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

static int apply;
module_param(apply, int, 0444);
MODULE_PARM_DESC(apply, "Refused. apply=1 crashed on 2026-09-21");

static int read_ext;
module_param(read_ext, int, 0444);
MODULE_PARM_DESC(read_ext, "1 = read dcpext1 disp-1 only, no panel, no writes");

static int __init dispclk_init(void)
{
	void __iomem *ext;
	int i, nonzero = 0, logged = 0;

	if (apply) {
		pr_err("dispclk: refusing apply=1 (crashed 2026-09-21)\n");
		return -EINVAL;
	}
	if (!read_ext) {
		pr_info("dispclk: loaded, not touching MMIO\n");
		return 0;
	}

	pr_info("dispclk: read-only dcpext1 disp-1 0x315320000\n");
	ext = ioremap(DCPEXT_DISP1, DISP_SIZE);
	if (!ext)
		return -ENOMEM;
	for (i = 0; i < DISP_SIZE; i += 4) {
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
	pr_info("dispclk: dcpext1 disp-1 nonzero words %d\n", nonzero);
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
