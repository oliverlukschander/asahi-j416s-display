/* SPDX-License-Identifier: GPL-2.0-only */
/* Offline behavioral tests of the exact handshake used by apple.c. */
#include <assert.h>
#include <stdio.h>
#include "apple-dpin-handshake.h"

struct model {
	unsigned int control, ack, hpd, mode_a, mode_b;
	unsigned int writes, hpd_writes, mode_writes, waits, reads;
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
	case APPLE_DPIN_MODE_A: return m->mode_a;
	case APPLE_DPIN_MODE_B: return m->mode_b;
	default: assert(0); return 0;
	}
}

static void model_write(void *ctx, unsigned int offset, unsigned int value)
{
	struct model *m = ctx;

	switch (offset) {
	case APPLE_DPIN_HPD:
		/* Only the CONNECTED bit may change; never invents HPD_LEVEL. */
		assert(((value ^ m->hpd) & ~APPLE_DPIN_CONNECTED) == 0);
		m->hpd = value;
		m->hpd_writes++;
		return;
	case APPLE_DPIN_MODE_A:
		/* Clears the low byte, sets exactly one bit at MODE_VALUE. */
		assert(value == ((m->mode_a & ~0xffU) | (1U << APPLE_DPIN_MODE_VALUE)));
		m->mode_a = value;
		m->mode_writes++;
		return;
	case APPLE_DPIN_MODE_B:
		/* Pure OR of MODE_VALUE at bit 7; no bits ever cleared. */
		assert(value == (m->mode_b | (APPLE_DPIN_MODE_VALUE << 7)));
		m->mode_b = value;
		m->mode_writes++;
		return;
	default:
		assert(offset == APPLE_DPIN_CONTROL);
		assert(((value ^ m->control) & ~(APPLE_DPIN_INACTIVE | APPLE_DPIN_CONNECTED)) == 0);
		m->control = value;
		m->writes++;
	}
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
	/*
	 * Delayed firmware acknowledgement. A successful activation also sets
	 * CONNECTED on HPD and CONTROL (native bringConnectionUp, not rolled
	 * back since the handshake succeeded); unrelated control bits survive.
	 */
	m = (struct model){ .hpd = 4, .control = 0xa5, .ack = 1, .ack_after = 3 };
	assert(run(&m, 1) == 0 && m.control == 0xa6 && m.waits == 3);
	assert(m.hpd == 6 && m.hpd_writes == 1);
	assert(m.mode_a == 0x200 && m.mode_b == 0x480 && m.mode_writes == 2);
	/* Deactivation does not require HPD high, never writes HPD, and waits
	 * for inactive ACK.
	 */
	m = (struct model){ .control = 0xa4, .ack_after = 2 };
	assert(run(&m, 0) == 0 && m.control == 0xa5 && m.waits == 2);
	assert(m.hpd_writes == 0 && m.mode_writes == 0);
	/*
	 * Deadline is bounded; rollback restores both bits this driver owns
	 * (INACTIVE and CONNECTED) to their pre-handshake values while
	 * preserving hardware changes to other control bits. HPD is not
	 * rolled back (native teardown for it was never traced), so its
	 * CONNECTED bit stays set even though activation failed.
	 */
	m = (struct model){ .hpd = 4, .control = 0xa5, .ack = 1,
		.change_other_bits = 1 };
	assert(run(&m, 1) == -ETIMEDOUT);
	assert(m.waits == 10 && m.writes == 2 && m.control == 0x1a5);
	assert(m.hpd == 6 && m.hpd_writes == 1);
	assert(m.mode_a == 0x200 && m.mode_b == 0x480 && m.mode_writes == 2);
	/* A dropped sink interrupts polling; no synthetic reset writes beyond
	 * the owned-bits rollback.
	 */
	m = (struct model){ .hpd = 4, .control = 0xa5, .ack = 1, .drop_after = 2 };
	assert(run(&m, 1) == -ENOLINK && m.waits == 2 && m.control == 0xa5);
	assert(m.mode_a == 0x200 && m.mode_b == 0x480 && m.mode_writes == 2);
	/* An already acknowledged state needs no polling. */
	m = (struct model){ .hpd = 4, .control = 0xa4 };
	assert(run(&m, 1) == 0 && m.waits == 0);
	assert(m.mode_a == 0x200 && m.mode_b == 0x480 && m.mode_writes == 2);
	/* Invalid ACK is an error, never a fabricated successful activation. */
	m = (struct model){ .hpd = 4, .control = 0xa5, .ack = ~0U };
	assert(run(&m, 1) == -EIO && m.control == 0xa5);
	assert(m.mode_a == 0x200 && m.mode_b == 0x480 && m.mode_writes == 2);
	puts("9 native DP-IN handshake scenarios passed (mock registers only)");
	return 0;
}
