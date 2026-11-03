#include <linux/module.h>
#define INCLUDE_VERMAGIC
#include <linux/build-salt.h>
#include <linux/elfnote-lto.h>
#include <linux/export-internal.h>
#include <linux/vermagic.h>
#include <linux/compiler.h>

#ifdef CONFIG_UNWINDER_ORC
#include <asm/orc_header.h>
ORC_HEADER;
#endif

BUILD_SALT;
BUILD_LTO_INFO;

MODULE_INFO(vermagic, VERMAGIC_STRING);
MODULE_INFO(name, KBUILD_MODNAME);

__visible struct module __this_module
__section(".gnu.linkonce.this_module") = {
	.name = KBUILD_MODNAME,
	.init = init_module,
#ifdef CONFIG_MODULE_UNLOAD
	.exit = cleanup_module,
#endif
	.arch = MODULE_ARCH_INIT,
};

#ifdef CONFIG_RETPOLINE
MODULE_INFO(retpoline, "Y");
#endif



static const struct modversion_info ____versions[]
__used __section("__versions") = {
	{ 0x57bc19d2, "down_write" },
	{ 0xce807a25, "up_write" },
	{ 0x4a3ad70e, "wait_for_completion_timeout" },
	{ 0x65487097, "__x86_indirect_thunk_rax" },
	{ 0xe2c17b5d, "__SCT__might_resched" },
	{ 0xf0fdf6cb, "__stack_chk_fail" },
	{ 0x13c49cc2, "_copy_from_user" },
	{ 0x2cf0c910, "sg_init_table" },
	{ 0x6b10bee1, "_copy_to_user" },
	{ 0xfca6cab, "module_put" },
	{ 0x9f3bd1c3, "dma_free_attrs" },
	{ 0x4c5bdb9c, "put_device" },
	{ 0x37a0cba, "kfree" },
	{ 0x8adf66df, "misc_deregister" },
	{ 0x5f1ea823, "dma_release_channel" },
	{ 0xa193b721, "devm_kmalloc" },
	{ 0x4c03a563, "random_kmalloc_seed" },
	{ 0x8da0819, "kmalloc_caches" },
	{ 0xd0c3484c, "kmalloc_trace" },
	{ 0xcdef0d31, "dma_request_chan" },
	{ 0x9d4296b0, "get_device" },
	{ 0x6f584963, "dma_set_mask" },
	{ 0xfe15742c, "_dev_err" },
	{ 0xf1a358b2, "dma_set_coherent_mask" },
	{ 0xac5bfa41, "dma_alloc_attrs" },
	{ 0xcefb0c9f, "__mutex_init" },
	{ 0x608741b5, "__init_swait_queue_head" },
	{ 0x792e9fd, "misc_register" },
	{ 0xbdfb6dbb, "__fentry__" },
	{ 0x23509fba, "__platform_driver_register" },
	{ 0x5b8239ca, "__x86_return_thunk" },
	{ 0xa6257a2f, "complete" },
	{ 0x4a77885d, "platform_driver_unregister" },
	{ 0x4dfa8d4b, "mutex_lock" },
	{ 0x3213f038, "mutex_unlock" },
	{ 0x296695f, "refcount_warn_saturate" },
	{ 0x54b1fac6, "__ubsan_handle_load_invalid_value" },
	{ 0x9180460f, "__module_get" },
	{ 0xba2484cc, "dma_mmap_attrs" },
	{ 0xe2fd41e5, "module_layout" },
};

MODULE_INFO(depends, "");

MODULE_ALIAS("of:N*T*Crasterix,dma-proxy-v1");
MODULE_ALIAS("of:N*T*Crasterix,dma-proxy-v1C*");

MODULE_INFO(srcversion, "3EFC40DBD66F6E491587BDA");
