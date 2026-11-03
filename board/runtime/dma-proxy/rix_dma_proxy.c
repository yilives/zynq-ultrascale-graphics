// SPDX-License-Identifier: GPL-3.0-or-later
// ABI-compatible board replacement for RasterIX's ARM32 example dma-proxy.
#include "dma-proxy.h"
#include <linux/completion.h>
#include <linux/compat.h>
#include <linux/dma-mapping.h>
#include <linux/dmaengine.h>
#include <linux/fs.h>
#include <linux/kref.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/stringify.h>
#include <linux/uaccess.h>
#include <linux/version.h>

struct rix_channel {
    struct miscdevice misc;
    struct dma_chan *chan;
    struct device *dma_dev;
    struct channel_buffer *buffers;
    dma_addr_t dma_base;
    struct mutex lock;
    struct completion done;
    struct kref refs;
    enum dma_transfer_direction direction;
    dma_cookie_t cookie;
    u32 index;
    bool active, opened, offline;
};
struct rix_proxy { struct rix_channel *channels[2]; };
#define MAP_BYTES (sizeof(struct channel_buffer) * BUFFER_COUNT)
static void rix_free(struct kref *ref)
{
    struct rix_channel *c=container_of(ref,struct rix_channel,refs);
    dma_free_coherent(c->dma_dev,MAP_BYTES,c->buffers,c->dma_base);
    put_device(c->dma_dev);
    kfree(c);
}
static void rix_complete(void *arg) { complete(arg); }
static int rix_start(struct rix_channel *c,u32 id)
{
    struct dma_async_tx_descriptor *desc;
    u32 length=READ_ONCE(c->buffers[id].length);
    if(c->active) return -EBUSY;
    if(!length||length>BUFFER_SIZE||(length&3)) return -EINVAL;
    reinit_completion(&c->done);
    dma_wmb();
    desc=dmaengine_prep_slave_single(c->chan,c->dma_base+id*sizeof(struct channel_buffer),
        length,c->direction,DMA_CTRL_ACK|DMA_PREP_INTERRUPT);
    if(!desc) return -EIO;
    desc->callback=rix_complete;desc->callback_param=&c->done;
    c->cookie=dmaengine_submit(desc);
    if(dma_submit_error(c->cookie)) return -EIO;
    c->index=id;c->active=true;
    WRITE_ONCE(c->buffers[id].status,PROXY_BUSY);
    dma_async_issue_pending(c->chan);
    return 0;
}
static int rix_finish(struct rix_channel *c,u32 id)
{
    int ret=0;
    if(!c->active||id!=c->index) return -EINVAL;
    if(!wait_for_completion_timeout(&c->done,msecs_to_jiffies(3000))) ret=-ETIMEDOUT;
    else if(dma_async_is_tx_complete(c->chan,c->cookie,NULL,NULL)!=DMA_COMPLETE) ret=-EIO;
    // Synchronously remove callbacks before allowing buffer reuse.
    if(ret) dmaengine_terminate_sync(c->chan);
    dma_rmb();c->active=false;
    WRITE_ONCE(c->buffers[id].status,ret==-ETIMEDOUT?PROXY_TIMEOUT:ret?PROXY_ERROR:PROXY_NO_ERROR);
    return ret;
}
static long rix_ioctl(struct file *file,unsigned int cmd,unsigned long arg)
{
    struct rix_channel *c=file->private_data;
    u32 id;long ret;
    if(cmd==RIX_DMA_GET_ABI) { id=RIX_DMA_ABI_VERSION;return copy_to_user((void __user *)arg,&id,sizeof(id))?-EFAULT:0; }
    if(cmd!=START_XFER&&cmd!=FINISH_XFER&&cmd!=XFER) return -ENOTTY;
    if(copy_from_user(&id,(void __user *)arg,sizeof(id))) return -EFAULT;
    if(id>=BUFFER_COUNT) return -EINVAL;
    mutex_lock(&c->lock);
    if(c->offline) {ret=-ENODEV;goto out;}
    ret=cmd==FINISH_XFER?rix_finish(c,id):rix_start(c,id);
    if(!ret&&cmd==XFER) ret=rix_finish(c,id);
out: mutex_unlock(&c->lock);return ret;
}
#ifdef CONFIG_COMPAT
static long rix_compat_ioctl(struct file *file,unsigned int cmd,unsigned long arg)
{
    return rix_ioctl(file,cmd,(unsigned long)compat_ptr(arg));
}
#endif
static int rix_open(struct inode *inode,struct file *file)
{
    struct rix_channel *c=container_of(file->private_data,struct rix_channel,misc);
    int ret=0;
    mutex_lock(&c->lock);
    if(c->offline) ret=-ENODEV;
    else if(c->opened) ret=-EBUSY;
    else {c->opened=true;kref_get(&c->refs);file->private_data=c;}
    mutex_unlock(&c->lock);return ret;
}
static int rix_release(struct inode *inode,struct file *file)
{
    struct rix_channel *c=file->private_data;
    mutex_lock(&c->lock);
    if(!c->offline) {
        // AXI DMA soft reset affects both directions. An idle close must
        // preserve the peer channel's IRQ enables; only drain callbacks.
        if(c->active) dmaengine_terminate_sync(c->chan);
        else dmaengine_synchronize(c->chan);
    }
    c->active=false;c->opened=false;
    mutex_unlock(&c->lock);kref_put(&c->refs,rix_free);return 0;
}
static void rix_vma_open(struct vm_area_struct *vma)
{
    struct rix_channel *c=vma->vm_private_data;
    __module_get(THIS_MODULE);kref_get(&c->refs);
}
static void rix_vma_close(struct vm_area_struct *vma)
{
    struct rix_channel *c=vma->vm_private_data;
    kref_put(&c->refs,rix_free);module_put(THIS_MODULE);
}
static const struct vm_operations_struct rix_vm_ops={.open=rix_vma_open,.close=rix_vma_close};
static int rix_mmap(struct file *file,struct vm_area_struct *vma)
{
    struct rix_channel *c=file->private_data;
    int ret;
    if(vma->vm_pgoff||vma->vm_end-vma->vm_start!=PAGE_ALIGN(MAP_BYTES)) return -EINVAL;
    mutex_lock(&c->lock);
    if(c->offline) {ret=-ENODEV;goto out;}
    ret=dma_mmap_coherent(c->dma_dev,vma,c->buffers,c->dma_base,MAP_BYTES);
    if(!ret) {
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6,3,0)
        vm_flags_set(vma,VM_DONTEXPAND|VM_DONTDUMP);
#else
        vma->vm_flags|=VM_DONTEXPAND|VM_DONTDUMP;
#endif
        vma->vm_private_data=c;vma->vm_ops=&rix_vm_ops;rix_vma_open(vma);
    }
out: mutex_unlock(&c->lock);return ret;
}
static const struct file_operations rix_fops={
    .owner=THIS_MODULE,.open=rix_open,.release=rix_release,.mmap=rix_mmap,
    .unlocked_ioctl=rix_ioctl,
#ifdef CONFIG_COMPAT
    .compat_ioctl=rix_compat_ioctl,
#endif
};
static void rix_remove_channel(struct rix_channel *c)
{
    if(!c) return;
    misc_deregister(&c->misc);
    mutex_lock(&c->lock);c->offline=true;
    dmaengine_terminate_sync(c->chan);c->active=false;
    dma_release_channel(c->chan);
    mutex_unlock(&c->lock);kref_put(&c->refs,rix_free);
}
static int rix_probe(struct platform_device *pdev)
{
    static const char * const names[]={"dma_proxy_tx","dma_proxy_rx"};
    struct rix_proxy *p;int i,ret;
    BUILD_BUG_ON(sizeof(struct channel_buffer)!=BUFFER_SIZE+1024);
    p=devm_kzalloc(&pdev->dev,sizeof(*p),GFP_KERNEL);
    if(!p) return -ENOMEM;
    for(i=0;i<2;i++) {
        struct rix_channel *c=kzalloc(sizeof(*c),GFP_KERNEL);
        if(!c) {ret=-ENOMEM;goto fail;}
        c->chan=dma_request_chan(&pdev->dev,names[i]);
        if(IS_ERR(c->chan)) {ret=PTR_ERR(c->chan);kfree(c);goto fail;}
        // AXI DMA uses the controller's device for DMA mappings on both the
        // supplied 5.4 BSP and modern kernels (not its channel sysfs device).
        c->dma_dev=get_device(c->chan->device->dev);
        ret=dma_set_mask_and_coherent(c->dma_dev,DMA_BIT_MASK(32));
        if(ret) goto free_channel;
        c->buffers=dma_alloc_coherent(c->dma_dev,MAP_BYTES,&c->dma_base,GFP_KERNEL);
        if(!c->buffers) {ret=-ENOMEM;goto free_channel;}
        if(c->dma_base+MAP_BYTES-1>U32_MAX) {ret=-ERANGE;dma_free_coherent(c->dma_dev,MAP_BYTES,c->buffers,c->dma_base);goto free_channel;}
        mutex_init(&c->lock);init_completion(&c->done);kref_init(&c->refs);
        c->direction=i?DMA_DEV_TO_MEM:DMA_MEM_TO_DEV;
        c->misc.minor=MISC_DYNAMIC_MINOR;c->misc.name=names[i];c->misc.fops=&rix_fops;
        c->misc.parent=&pdev->dev;c->misc.mode=0600;
        ret=misc_register(&c->misc);
        if(ret) {dma_release_channel(c->chan);kref_put(&c->refs,rix_free);goto fail;}
        p->channels[i]=c;continue;
free_channel:
        put_device(c->dma_dev);dma_release_channel(c->chan);kfree(c);goto fail;
    }
    platform_set_drvdata(pdev,p);return 0;
fail:
    while(i--) rix_remove_channel(p->channels[i]);
    if(ret!=-EPROBE_DEFER)
        dev_err(&pdev->dev,"DMA proxy initialization failed: %d\n",ret);
    return ret;
}
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6,11,0)
static void rix_remove(struct platform_device *pdev)
#else
static int rix_remove(struct platform_device *pdev)
#endif
{
    struct rix_proxy *p=platform_get_drvdata(pdev);
    rix_remove_channel(p->channels[1]);rix_remove_channel(p->channels[0]);
#if LINUX_VERSION_CODE < KERNEL_VERSION(6,11,0)
    return 0;
#endif
}
static const struct of_device_id rix_match[]={ {.compatible="rasterix,dma-proxy-v1"},{} };
MODULE_DEVICE_TABLE(of,rix_match);
static struct platform_driver rix_driver={.probe=rix_probe,.remove=rix_remove,.driver={.name="rix-dma-proxy",.of_match_table=rix_match}};
module_platform_driver(rix_driver);
MODULE_LICENSE("GPL");
MODULE_INFO(rix_dma_abi,__stringify(RIX_DMA_ABI_VERSION));
MODULE_INFO(rix_dma_buffers,__stringify(BUFFER_COUNT));
MODULE_DESCRIPTION("RasterIX fixed-width DMA proxy for AArch64");
