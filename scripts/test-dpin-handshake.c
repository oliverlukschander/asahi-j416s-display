/* SPDX-License-Identifier: GPL-2.0-only */
/* Offline behavioral tests of the exact handshake used by apple.c. */
#include <assert.h>
#include <stdio.h>
#include "apple-dpin-handshake.h"

struct model {
	unsigned int control, ack, hpd;
	unsigned int writes, waits, reads;
	int ack_after, drop_after, change_other_bits;
};

static unsigned int model_read(void *ctx, unsigned int offset)
{
	struct model *m = ctx;

	m->reads++;
	switch (offset) {
	case APPLE_DPIN_HPD: return m->hpd;
	case APPLE_DPIN_CONTROL: return m->control;
	case APPLE_DPIN_ACK: return m->ack;
	default: assert(0); return 0;
	}
}

static void model_write(void *ctx, unsigned int offset, unsigned int value)
{
	struct model *m = ctx;

	assert(offset == APPLE_DPIN_CONTROL);
	assert(((value ^ m->control) & ~1U) == 0);
	m->control = value;
	m->writes++;
}

static int model_wait(void *ctx)
{
	struct model *m = ctx;

	m->waits++;
	if ((int)m->waits == m->ack_after)
		m->ack = m->control & 1;
	if ((int)m->waits == m->drop_after)
		m->hpd = 0;
	if (m->change_other_bits)
		m->control |= 0x100;
	return m->waits >= 10 ? -ETIMEDOUT : 0;
}

static int run(struct model *m, int active)
{
	struct apple_dpin_io io = {
		.read = model_read, .write = model_write,
		.wait = model_wait, .ctx = m,
	};
	return apple_dpin_handshake(&io, active);
}

int main(void)
{
	struct model m;

	/* An absent sink must cause no write, even if the control is inactive. */
	m = (struct model){ .control = 0xa5, .ack = 1 };
	assert(run(&m, 1) == -ENOLINK && m.writes == 0);
	/* Reject a floating register window before writing. */
	m = (struct model){ .hpd = ~0U };
	assert(run(&m, 1) == -EIO && m.writes == 0);
	m = (struct model){ .hpd = 4, .control = ~0U };
	assert(run(&m, 1) == -EIO && m.writes == 0);
	/* Delayed firmware acknowledgement; unrelated control bits survive. */
	m = (struct model){ .hpd = 4, .control = 0xa5, .ack = 1, .ack_after = 3 };
	assert(run(&m, 1) == 0 && m.control == 0xa4 && m.waits == 3);
	/* Deactivation does not require HPD high and waits for inactive ACK. */
	m = (struct model){ .control = 0xa4, .ack_after = 2 };
	assert(run(&m, 0) == 0 && m.control == 0xa5 && m.waits == 2);
	/* Deadline is bounded; rollback preserves hardware changes to other bits. */
	m = (struct model){ .hpd = 4, .control = 0xa5, .ack = 1,
		.change_other_bits = 1 };
	assert(run(&m, 1) == -ETIMEDOUT);
	assert(m.waits == 10 && m.writes == 2 && m.control == 0x1a5);
	/* A dropped sink interrupts polling; no synthetic HPD or reset writes. */
	m = (struct model){ .hpd = 4, .control = 0xa5, .ack = 1, .drop_after = 2 };
	assert(run(&m, 1) == -ENOLINK && m.waits == 2 && m.control == 0xa5);
	/* An already acknowledged state needs no polling. */
	m = (struct model){ .hpd = 4, .control = 0xa4 };
	assert(run(&m, 1) == 0 && m.waits == 0);
	/* Invalid ACK is an error, never a fabricated successful activation. */
	m = (struct model){ .hpd = 4, .control = 0xa5, .ack = ~0U };
	assert(run(&m, 1) == -EIO && m.control == 0xa5);
	puts("9 native DP-IN handshake scenarios passed (mock registers only)");
	return 0;
}
