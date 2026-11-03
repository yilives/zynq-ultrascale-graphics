// SPDX-License-Identifier: GPL-3.0-or-later
#include "plgpu-display.h"
#include <linux/delay.h>
#include <linux/compat.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/jiffies.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_reserved_mem.h>
#include <linux/platform_device.h>
#include <linux/sizes.h>
#include <linux/uaccess.h>
#include <linux/version.h>
#include <linux/kref.h>
struct plgpu {
    struct miscdevice misc;
    struct mutex lock;
    struct kref refs;
    void __iomem *regs;
    bool offline;
};
static void display_free(struct kref *ref) { kfree(container_of(ref,struct plgpu,refs)); }
static void get_status(struct plgpu *d,struct plgpu_status *s)
{
    int i;u32 *counters=&s->frame_id;
    memset(s,0,sizeof(*s));
    s->abi=readl(d->regs);s->configuration=readl(d->regs+0x0c);
    s->status=readl(d->regs+8);s->enabled=readl(d->regs+4);
    writel(1,d->regs+0x40); // Snapshot all GPU-domain counters together.
    for(i=0;i<12;i++) counters[i]=readl(d->regs+0x10+i*4);
}
static long display_ioctl(struct file *file,unsigned int cmd,unsigned long arg)
{
    struct plgpu *d=file->private_data;
    struct plgpu_status status;
    struct plgpu_wait wait;
    unsigned long deadline;
    u32 enabled;long ret=0;
    mutex_lock(&d->lock);
    if(d->offline) {ret=-ENODEV;goto out;}
    switch(cmd) {
    case PLGPU_GET_STATUS:
        get_status(d,&status);
        ret=copy_to_user((void __user *)arg,&status,sizeof(status))?-EFAULT:0;break;
    case PLGPU_ENABLE:
        if(copy_from_user(&enabled,(void __user *)arg,sizeof(enabled))) {ret=-EFAULT;break;}
        if(enabled>1) {ret=-EINVAL;break;}
        get_status(d,&status);
        if(enabled&&((status.status&3)!=3||(status.status&4))) {ret=-EIO;break;}
        writel(enabled,d->regs+4);
        if(readl(d->regs+4)!=enabled) ret=-EIO;
        break;
    case PLGPU_WAIT_PRESENT:
        if(copy_from_user(&wait,(void __user *)arg,sizeof(wait))) {ret=-EFAULT;break;}
        if(!wait.timeout_ms||wait.timeout_ms>30000) {ret=-EINVAL;break;}
        deadline=jiffies+msecs_to_jiffies(wait.timeout_ms);
        for(;;) {
            get_status(d,&status);
            if(status.status&4) {ret=-EIO;break;}
            if(status.presented&&(s32)(status.last_presented_id-wait.frame_id)>=0) break;
            if(time_after_eq(jiffies,deadline)) {ret=-ETIMEDOUT;break;}
            // Release the lock while sleeping so remove/other status users work.
            mutex_unlock(&d->lock);
            if(msleep_interruptible(2)) ret=-ERESTARTSYS;
            mutex_lock(&d->lock);
            if(ret) break;
            if(d->offline) {ret=-ENODEV;break;}
        }
        break;
    default:ret=-ENOTTY;
    }
out:mutex_unlock(&d->lock);return ret;
}
#ifdef CONFIG_COMPAT
static long display_compat_ioctl(struct file *file,unsigned int cmd,unsigned long arg)
{
    return display_ioctl(file,cmd,(unsigned long)compat_ptr(arg));
}
#endif
static int display_open(struct inode *inode,struct file *file)
{
    struct plgpu *d=container_of(file->private_data,struct plgpu,misc);
    int ret=0;
    mutex_lock(&d->lock);
    if(d->offline) ret=-ENODEV;
    else {kref_get(&d->refs);file->private_data=d;}
    mutex_unlock(&d->lock);return ret;
}
static int display_release(struct inode *inode,struct file *file)
{
    kref_put(&((struct plgpu *)file->private_data)->refs,display_free);return 0;
}
static const struct file_operations display_fops={.owner=THIS_MODULE,.open=display_open,
    .release=display_release,.unlocked_ioctl=display_ioctl,
#ifdef CONFIG_COMPAT
    .compat_ioctl=display_compat_ioctl,
#endif
};
static int display_probe(struct platform_device *pdev)
{
    struct plgpu *d;struct device_node *node;struct reserved_mem *mem;int ret;
    node=of_parse_phandle(pdev->dev.of_node,"memory-region",0);
    if(!node) return -EINVAL;
    mem=of_reserved_mem_lookup(node);of_node_put(node);
    if(!mem||mem->size!=SZ_32M||mem->base+mem->size>1ULL<<32) return -ERANGE;
    d=kzalloc(sizeof(*d),GFP_KERNEL);if(!d) return -ENOMEM;
    d->regs=devm_platform_ioremap_resource(pdev,0);
    if(IS_ERR(d->regs)) {ret=PTR_ERR(d->regs);goto fail;}
    if(readl(d->regs)!=0x52495801||readl(d->regs+0x44)!=mem->base||readl(d->regs+0x48)!=mem->size) {ret=-EINVAL;goto fail;}
    mutex_init(&d->lock);kref_init(&d->refs);
    d->misc.minor=MISC_DYNAMIC_MINOR;d->misc.name="plgpu_display";
    d->misc.fops=&display_fops;d->misc.parent=&pdev->dev;d->misc.mode=0600;
    ret=misc_register(&d->misc);if(ret) goto fail;
    platform_set_drvdata(pdev,d);return 0;
fail:kfree(d);return ret;
}
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6,11,0)
static void display_remove(struct platform_device *pdev)
#else
static int display_remove(struct platform_device *pdev)
#endif
{
    struct plgpu *d=platform_get_drvdata(pdev);
    misc_deregister(&d->misc);mutex_lock(&d->lock);
    d->offline=true;writel(0,d->regs+4);mutex_unlock(&d->lock);
    kref_put(&d->refs,display_free);
#if LINUX_VERSION_CODE < KERNEL_VERSION(6,11,0)
    return 0;
#endif
}
static const struct of_device_id display_match[]={ {.compatible="rasterix,plgpu-display-v1"},{} };
MODULE_DEVICE_TABLE(of,display_match);
static struct platform_driver display_driver={.probe=display_probe,.remove=display_remove,
    .driver={.name="plgpu-display",.of_match_table=display_match}};
module_platform_driver(display_driver);
MODULE_LICENSE("GPL");
