// SPDX-License-Identifier: GPL-2.0-only OR MIT
/*
 * Compare the running panel's disp-1 block with dcpext1 and copy words
 * that are on for the panel and zero on dcpext1. Never writes the panel.
 * Not loaded from the initramfs.
 */

#include <linux/io.h>
#include <linux/module.h>
#include <linux/slab.h>

#define DISP_SIZE		0x4000
#define PANEL_DISP1		0x389320000ULL
#define DCPEXT_DISP1		0x315320000ULL
#define XBAR_BASE		0x70304c000ULL

static int apply;
module_param(apply, int, 0444);
MODULE_PARM_DESC(apply, "Must stay 0. apply=1 ioremaps disp-1 and crashed on 2026-09-21");

static void dispclk_xbar(const char *tag)
{
	void __iomem *xbar;
	u32 c000, s800, c020, s820, c024, s81c;

	xbar = ioremap(XBAR_BASE, 0x1000);
	if (!xbar) {
		pr_err("dispclk: crossbar map failed\n");
		return;
	}
	c000 = readl(xbar + 0x000);
	s800 = readl(xbar + 0x800);
	c020 = readl(xbar + 0x020);
	s820 = readl(xbar + 0x820);
	c024 = readl(xbar + 0x024);
	s81c = readl(xbar + 0x81c);
	iounmap(xbar);
	pr_info("dispclk: %s xbar 000=%08x 800=%08x 020=%08x 820=%08x 024=%08x 81c=%08x\n",
		tag, c000, s800, c020, s820, c024, s81c);
}

static int __init dispclk_init(void)
{
	void __iomem *panel_io, *ext_io;

	if (!apply) {
		pr_info("dispclk: loaded, not touching MMIO\n");
		return 0;
	}
	u32 *panel, *ext;
	int i, n = 0, stuck = 0, logged = 0;

	panel = kzalloc(DISP_SIZE, GFP_KERNEL);
	ext = kzalloc(DISP_SIZE, GFP_KERNEL);
	if (!panel || !ext) {
		kfree(panel);
		kfree(ext);
		return -ENOMEM;
	}

	panel_io = ioremap(PANEL_DISP1, DISP_SIZE);
	ext_io = ioremap(DCPEXT_DISP1, DISP_SIZE);
	if (!panel_io || !ext_io) {
		pr_err("dispclk: map failed panel=%d ext=%d\n",
		       panel_io != NULL, ext_io != NULL);
		if (panel_io)
			iounmap(panel_io);
		if (ext_io)
			iounmap(ext_io);
		kfree(panel);
		kfree(ext);
		return -ENOMEM;
	}

	memcpy_fromio(panel, panel_io, DISP_SIZE);
	memcpy_fromio(ext, ext_io, DISP_SIZE);
	iounmap(panel_io);

	dispclk_xbar("before");

	for (i = 0; i < DISP_SIZE / 4; i++) {
		if (!panel[i] || ext[i])
			continue;
		if (logged < 40) {
			pr_info("dispclk: +%03x panel=%08x\n", i * 4, panel[i]);
			logged++;
		}
		n++;
		if (apply)
			writel(panel[i], ext_io + i * 4);
	}

	if (apply) {
		for (i = 0; i < DISP_SIZE / 4; i++) {
			if (!panel[i] || ext[i])
				continue;
			if (readl(ext_io + i * 4) == panel[i])
				stuck++;
		}
	}
	iounmap(ext_io);

	pr_info("dispclk: copied %d words, %d stuck, apply=%d\n",
		n, stuck, apply);
	dispclk_xbar("after");

	kfree(panel);
	kfree(ext);
	return 0;
}

static void __exit dispclk_exit(void)
{
}

module_init(dispclk_init);
module_exit(dispclk_exit);
MODULE_DESCRIPTION("Copy panel disp-1 clock words onto dcpext1");
MODULE_LICENSE("GPL");
MODULE_AUTHOR("Oliver Lukschander <oliver.lukschander@golf.at>");
