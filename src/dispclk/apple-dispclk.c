// SPDX-License-Identifier: GPL-2.0-only OR MIT
/*
 * Read dcpext1 disp-1 only. The 2026-09-21 crash mapped the live panel
 * block and wrote this block. This module does neither unless a
 * parameter that is refused is set.
 */

#include <linux/io.h>
#include <linux/module.h>

#define DISP_SIZE	0x4000
#define DCPEXT_DISP1	0x315320000ULL
#define DCPEXT_DISP2	0x315344000ULL
#define PANEL_DISP2	0x389344000ULL
#define DCPEXT_DISP0	0x314000000ULL
#define DISP0_READ	0x1000

static int apply;
module_param(apply, int, 0444);
MODULE_PARM_DESC(apply, "Refused. apply=1 crashed on 2026-09-21");

static int read_ext;
module_param(read_ext, int, 0444);
MODULE_PARM_DESC(read_ext, "1 = read dcpext1 disp-1 only, no panel, no writes");

static int read_ext2;
module_param(read_ext2, int, 0444);
MODULE_PARM_DESC(read_ext2, "1 = read dcpext1 disp-2 only, no panel, no writes");

static int read_panel2;
module_param(read_panel2, int, 0444);
MODULE_PARM_DESC(read_panel2, "1 = read panel disp-2 only, no writes");

static int read_ext0;
module_param(read_ext0, int, 0444);
MODULE_PARM_DESC(read_ext0, "1 = read first 4KB of dcpext1 disp-0 only");

static int write_074;
module_param(write_074, int, 0444);
MODULE_PARM_DESC(write_074, "1 = set dcpext1 disp-2 +074 to 0");

static int __init dispclk_init(void)
{
	void __iomem *ext;
	int i, nonzero = 0, logged = 0, size = DISP_SIZE;
	const char *label;

	if (apply) {
		pr_err("dispclk: refusing apply=1 (crashed 2026-09-21)\n");
		return -EINVAL;
	}
	if (write_074) {
		pr_err("dispclk: refusing write_074\n");
		return -EINVAL;
	}
	if (!read_ext && !read_ext2 && !read_panel2 && !read_ext0) {
		pr_info("dispclk: loaded, not touching MMIO\n");
		return 0;
	}

	if (read_ext0) {
		label = "dcpext1 disp-0";
		size = DISP0_READ;
		pr_info("dispclk: read-only dcpext1 disp-0 0x314000000\n");
		ext = ioremap(DCPEXT_DISP0, size);
	} else if (read_panel2) {
		label = "panel disp-2";
		pr_info("dispclk: read-only panel disp-2 0x389344000\n");
		ext = ioremap(PANEL_DISP2, size);
	} else {
		label = read_ext2 ? "dcpext1 disp-2" : "dcpext1 disp-1";
		pr_info("dispclk: read-only %s\n", label);
		ext = ioremap(read_ext2 ? DCPEXT_DISP2 : DCPEXT_DISP1, size);
	}
	if (!ext)
		return -ENOMEM;
	for (i = 0; i < size; i += 4) {
		u32 v = readl(ext + i);

		if (!v)
			continue;
		nonzero++;
		if (logged < 24) {
			pr_info("dispclk: +%03x %08x\n", i, v);
			logged++;
		}
	}
	iounmap(ext);
	pr_info("dispclk: %s nonzero words %d\n", label, nonzero);
	return 0;
}

static void __exit dispclk_exit(void)
{
}

module_init(dispclk_init);
module_exit(dispclk_exit);
MODULE_DESCRIPTION("Read dcpext1 disp-1 only");
MODULE_LICENSE("GPL");
MODULE_AUTHOR("Oliver Lukschander <oliver.lukschander@golf.at>");
