// SPDX-License-Identifier: GPL-2.0-or-later
/* Exclusive, coherent-memory geometry jobs. No user supplied DMA address. */
#include <linux/module.h>
#include <linux/miscdevice.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/dma-mapping.h>
#include <linux/platform_device.h>
#include <linux/uaccess.h>
#include <linux/mutex.h>
#include <linux/mm.h>
#include "rix-geometry.h"
#include "geometry-csr-layout.h"
#define PROFILE_MAGIC 0x4a324731u /* J2G1: only the integrated geometry image. */
static void __iomem *gpu,*regs;
static struct device *memory_device;
static void *pool;
static dma_addr_t pool_dma;
static DEFINE_MUTEX(job_mutex);
static atomic_t opened=ATOMIC_INIT(0);
static bool failed,pinned;
module_param(failed,bool,0444);
MODULE_PARM_DESC(failed,"An unfinished geometry transaction requires a board power cycle");
static bool identity(void)
{
 return readl(gpu)==0x52495801 && readl(gpu+0x0c)==0x9adb505e && readl(gpu+8)==3 &&
        readl(gpu+0xb0)==PROFILE_MAGIC && readl(gpu+0xb4)==2 &&
        readl(gpu+0xb8)==0 && readl(gpu+0xbc)==1;
}
static int execute(u32 mode,u32 count,u32 sequence,u64 *result)
{
 u32 control;int rc;
 if(failed)return -EIO;
 if(!identity())return -ENODEV; /* Never probe A004 on an absent-IP image. */
 control=readl(regs+GEO_CONTROL);
 if(!(control&4)||(control&0x81))return -EBUSY;
 writel(lower_32_bits(pool_dma),regs+GEO_MEM);
#if GEO_MEM_BITS == 64
 writel(0,regs+GEO_MEM+4);
#endif
 writel(mode,regs+GEO_MODE);writel(count,regs+GEO_COUNT);writel(sequence,regs+GEO_SEQUENCE);
 dma_wmb();writel(1,regs+GEO_CONTROL);
 rc=readl_poll_timeout(regs+GEO_CONTROL,control,control&2,10,2000000);
 if(rc){
  failed=true;
  if(!pinned){__module_get(THIS_MODULE);pinned=true;}
  pr_err("rix_geometry: unfinished AXI job; DMA pool pinned, board power cycle required\n");
  return rc;
 }
 dma_rmb();*result=(u64)readl(regs+GEO_RETURN)|((u64)readl(regs+GEO_RETURN+4)<<32);
 return 0;
}
static int geometry_open(struct inode *inode,struct file *file)
{
 if(failed)return -EIO;
 if(atomic_cmpxchg(&opened,0,1))return -EBUSY;
 return 0;
}
static int geometry_release(struct inode *inode,struct file *file)
{
 atomic_set(&opened,0);return 0;
}
static int geometry_mmap(struct file *file,struct vm_area_struct *vma)
{
 if(failed)return -EIO;
 if(vma->vm_pgoff || vma->vm_end-vma->vm_start!=RIX_GEOMETRY_POOL_BYTES)return -EINVAL;
 vma->vm_flags|=VM_DONTEXPAND|VM_DONTDUMP|VM_DONTCOPY;
 return dma_mmap_coherent(memory_device,vma,pool,pool_dma,RIX_GEOMETRY_POOL_BYTES);
}
static long geometry_ioctl(struct file *file,unsigned int command,unsigned long argument)
{
 struct rix_geometry_info info={RIX_GEOMETRY_MAGIC,RIX_GEOMETRY_ABI,RIX_GEOMETRY_POOL_BYTES,2048,
                               1024,1024,65536,131072,64,14336,PROFILE_MAGIC,0};
 struct rix_geometry_job job;u64 result;int rc;
 if(command==RIX_GEOMETRY_INFO){
  if(failed || !identity())return -ENODEV;
  return copy_to_user((void __user*)argument,&info,sizeof(info))?-EFAULT:0;
 }
 if(command!=RIX_GEOMETRY_SUBMIT)return -ENOTTY;
 if(copy_from_user(&job,(void __user*)argument,sizeof(job)))return -EFAULT;
 if(job.reserved || job.reserved_out[0] || job.reserved_out[1] ||
    (job.mode!=1 && job.mode!=2) || !job.count || job.count>2048 || !job.sequence)return -EINVAL;
 if(mutex_lock_interruptible(&job_mutex))return -ERESTARTSYS;
 rc=execute(job.mode,job.count,job.sequence,&result);
 if(!rc){job.records=(u32)result;job.status=(u32)(result>>32);
  if(job.records>14336 && !job.status){failed=true;rc=-EIO;}
 }
 mutex_unlock(&job_mutex);
 if(rc)return rc;
 return copy_to_user((void __user*)argument,&job,sizeof(job))?-EFAULT:0;
}
static const struct file_operations geometry_ops={
 .owner=THIS_MODULE,.open=geometry_open,.release=geometry_release,.mmap=geometry_mmap,
 .unlocked_ioctl=geometry_ioctl,
#ifdef CONFIG_COMPAT
 .compat_ioctl=geometry_ioctl,
#endif
};
static struct miscdevice geometry_device={.minor=MISC_DYNAMIC_MINOR,.name="rix-geometry",.fops=&geometry_ops,.mode=0600};
static int __init geometry_init(void)
{
 u64 result=0;int rc;
 gpu=ioremap(0xa0010000,4096);if(!gpu)return -ENOMEM;
 if(!identity()){rc=-ENODEV;goto fail_gpu;}
 regs=ioremap(0xa0040000,4096);if(!regs){rc=-ENOMEM;goto fail_gpu;}
 /* No-DDR protocol probe before allocation or accepting userspace jobs. */
 rc=execute(0,0,0,&result);if(rc || result!=RIX_GEOMETRY_MAGIC){rc=rc?rc:-ENODEV;goto fail_regs;}
 memory_device=bus_find_device_by_name(&platform_bus_type,NULL,"a0000000.dma");
 if(!memory_device){rc=-ENODEV;goto fail_regs;}
 if(memory_device->coherent_dma_mask<DMA_BIT_MASK(32)){rc=-EINVAL;goto fail_device;}
 pool=dma_alloc_coherent(memory_device,RIX_GEOMETRY_POOL_BYTES,&pool_dma,GFP_KERNEL);
 if(!pool){rc=-ENOMEM;goto fail_device;}
 if(upper_32_bits(pool_dma)||upper_32_bits(pool_dma+RIX_GEOMETRY_POOL_BYTES-1)){rc=-ERANGE;goto fail_pool;}
 rc=misc_register(&geometry_device);if(rc)goto fail_pool;
 pr_info("rix_geometry: J2G1/ABI1, exclusive 4MiB coherent pool, no PL FSR\n");return 0;
fail_pool:dma_free_coherent(memory_device,RIX_GEOMETRY_POOL_BYTES,pool,pool_dma);
fail_device:put_device(memory_device);
fail_regs:iounmap(regs);
fail_gpu:iounmap(gpu);return rc;
}
static void __exit geometry_exit(void)
{
 misc_deregister(&geometry_device);
 dma_free_coherent(memory_device,RIX_GEOMETRY_POOL_BYTES,pool,pool_dma);
 put_device(memory_device);iounmap(regs);iounmap(gpu);
}
module_init(geometry_init);module_exit(geometry_exit);
MODULE_LICENSE("GPL");MODULE_DESCRIPTION("RasterIX complete geometry frontend coherent command service");
