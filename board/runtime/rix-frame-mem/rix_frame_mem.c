// SPDX-License-Identifier: GPL-2.0-or-later
/* Normal-NC mapping of RAM-only HR slots and leased snapshot. No registers,
 * cached pages, arbitrary PFNs, GPU render slots, or startup hook. */
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/uaccess.h>
#include "rix-frame-mem.h"
static struct resource *frame_region;
static long frame_ioctl(struct file *file,unsigned int command,unsigned long arg)
{
 const struct rix_frame_mem_info info={RIX_FRAME_MEM_ABI,RIX_FRAME_MEM_BASE,RIX_FRAME_MEM_BYTES,RIX_FRAME_MEM_NORMAL_NC};
 if(command!=RIX_FRAME_MEM_INFO)return -ENOTTY;
 return copy_to_user((void __user *)arg,&info,sizeof(info))?-EFAULT:0;
}
static int frame_mmap(struct file *file,struct vm_area_struct *vma)
{
 /* Linux clears VM_SHARED for MAP_SHARED on an O_RDONLY file. MAYSHARE
  * retains the caller's sharing request without granting write permission. */
 if(!(vma->vm_flags&VM_MAYSHARE)||(vma->vm_flags&(VM_EXEC|VM_WRITE))||vma->vm_pgoff||
    vma->vm_end-vma->vm_start!=RIX_FRAME_MEM_BYTES)return -EINVAL;
 vma->vm_flags|=VM_IO|VM_PFNMAP|VM_DONTEXPAND|VM_DONTDUMP;
 vma->vm_flags&=~(VM_MAYEXEC|VM_MAYWRITE);
 /* On the matching ARM64 5.4 kernel this is MT_NORMAL_NC, with PXN/UXN.
  * No CPU caching: GPU ownership and barriers still determine visibility. */
 vma->vm_page_prot=pgprot_writecombine(vma->vm_page_prot);
 return remap_pfn_range(vma,vma->vm_start,RIX_FRAME_MEM_BASE>>PAGE_SHIFT,
                       RIX_FRAME_MEM_BYTES,vma->vm_page_prot);
}
static const struct file_operations frame_fops={.owner=THIS_MODULE,.unlocked_ioctl=frame_ioctl,.mmap=frame_mmap,.llseek=no_llseek};
static struct miscdevice frame_misc={.minor=MISC_DYNAMIC_MINOR,.name="rix-frame-mem",.fops=&frame_fops,.mode=0600};
static int __init frame_init(void)
{
 struct device_node *node;void __iomem *regs;u32 version,address,bytes;int ret;
 node=of_find_node_by_path("/rasterix-frame-snapshot");
 if(!node)return -ENODEV;
 ret=of_device_is_compatible(node,"rasterix,frame-snapshot-v1")&&of_device_is_available(node)&&
     !of_property_read_u32(node,"rasterix,snapshot-version",&version)&&version==1&&
     !of_property_read_u32(node,"rasterix,cpu-address",&address)&&address==0xa1400000&&
     !of_property_read_u32(node,"rasterix,bytes",&bytes)&&bytes==384000;
 of_node_put(node);if(!ret)return -ENODEV;
 node=of_find_node_by_path("/neural-style@a0030000");
 if(!node)return -ENODEV;
 ret=of_device_is_compatible(node,"rasterix,cnn-int8-v1")&&of_device_is_available(node);
 of_node_put(node);if(!ret)return -ENODEV;
 regs=ioremap(0xa0010000,4096);if(!regs)return -ENOMEM;
 ret=readl(regs)==0x52495801&&readl(regs+0x50)==0x50535431&&
     readl(regs+0x74)==0x534e5031&&readl(regs+0x88)==0xa1400000&&readl(regs+0x90)==384000;
 iounmap(regs);if(!ret)return -ENODEV;
 frame_region=request_mem_region(RIX_FRAME_MEM_BASE,RIX_FRAME_MEM_BYTES,"rasterix-frame-ram");
 if(!frame_region)return -EBUSY;
 ret=misc_register(&frame_misc);
 if(ret){release_mem_region(RIX_FRAME_MEM_BASE,RIX_FRAME_MEM_BYTES);return ret;}
 pr_info("rix-frame-mem: RFM1 read-only Normal-NC frame RAM at 0xa1000000, 6 MiB; MMIO excluded\n");
 return 0;
}
static void __exit frame_exit(void){misc_deregister(&frame_misc);release_mem_region(RIX_FRAME_MEM_BASE,RIX_FRAME_MEM_BYTES);}
module_init(frame_init);module_exit(frame_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Restricted RasterIX frame RAM Normal-NC mapping");
