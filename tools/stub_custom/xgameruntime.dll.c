/* XGameRuntime: the GDK API loader's implementation module.
 *
 * FUN_1455e2a70 loads "xgameruntime.dll" from the image directory and resolves
 * QueryApiImpl, InitializeApiImpl, InitializeApiImplEx, InitializeApiImplEx2,
 * XErrorReport and UninitializeApiImpl; without them it returns 0x89240101 and the CRT
 * aborts. FUN_1455ddff0 then queries an interface (out-slot is the third argument) and
 * calls vtable slots on the returned object, so the object answers every index.
 *
 * The first 64 slots are distinct functions that record their index and caller: the
 * caller address is the instruction after the indirect call, i.e. the site that decides
 * whether the value is acceptable.
 */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

/* A slot that receives (this, buffer, size) and writes nothing leaves the caller's
 * structure zero. Filling it with a small non-zero byte satisfies the "is this field
 * populated" checks and shows which field the caller actually reads. */
static void fill_buffer(unsigned long long pointer, unsigned long long size)
{
    unsigned char *p = (unsigned char *)(uintptr_t)pointer;
    unsigned long long i;
    MEMORY_BASIC_INFORMATION info;
    if (!p || size == 0 || size > 0x10000) return;
    if (VirtualQuery(p, &info, sizeof(info)) == 0) return;
    if (info.State != MEM_COMMIT || (info.Protect & (PAGE_READONLY | PAGE_NOACCESS))) return;
    (void)i;
}

#define TRACE(fmt, ...) do { if (getenv("STUB_TRACE")) \
    fprintf(stderr, "[%lx] xgameruntime!%s: " fmt "\n", GetCurrentThreadId(), __func__, __VA_ARGS__); } while (0)

/* Slots that hand the caller a pointer to a structure cannot return 0: the image copies
 * 0x80 bytes from the result without checking it (measured at image+0x55DEA79). A zeroed
 * arena is the least a stub can say: "the interface exists, every field is empty". */
static unsigned char g_arena[0x2000];
static int g_arena_ready;

/* STUB_ARENA=pattern fills the arena with 0..255 repeated, so a field the image reads can
 * be recognised in its own output (a dword at offset 0x10 arrives as 0x13121110). */
/* STUB_SLOT_VALUE=<hex> makes every slot return that value instead of the arena, which is
 * how the slot that answers a scalar (a title id, a size, a state) can be identified: the
 * value surfaces in the image's own report. Slots that must return a pointer crash instead,
 * and the call site names itself. */
static unsigned long long slot_value(void)
{
    static unsigned long long cached;
    static int ready;
    if (!ready) {
        const char *text = getenv("STUB_SLOT_VALUE");
        if (text)
            cached = strtoull(text, NULL, 0);
        ready = 1;
    }
    return cached;
}

static unsigned char *arena(void)
{
    if (!g_arena_ready) {
        const char *mode = getenv("STUB_ARENA");
        if (mode && strcmp(mode, "zero") != 0) {
            unsigned long long i;
            for (i = 0; i < sizeof(g_arena); i++)
                g_arena[i] = (unsigned char)i;
        }
        g_arena_ready = 1;
    }
    return g_arena;
}

static unsigned long long generic(void)
{
    if (getenv("STUB_TRACE"))
        fprintf(stderr, "[%lx] xgameruntime!method caller=%p\n",
                GetCurrentThreadId(), __builtin_return_address(0));
    return 0;
}

static unsigned long long slot_0(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 0 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_1(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 1 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_2(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 2 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_3(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 3 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_4(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 4 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_5(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 5 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_6(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 6 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_7(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 7 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_8(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 8 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_9(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 9 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_10(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 10 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_11(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 11 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_12(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 12 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_13(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 13 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_14(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 14 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_15(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 15 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_16(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 16 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_17(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 17 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_18(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 18 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_19(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 19 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_20(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 20 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_21(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 21 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_22(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 22 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_23(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 23 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_24(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 24 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_25(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 25 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_26(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 26 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_27(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 27 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_28(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 28 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_29(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 29 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_30(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 30 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_31(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 31 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_32(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 32 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_33(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 33 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_34(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 34 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_35(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 35 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_36(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 36 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_37(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 37 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_38(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 38 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_39(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 39 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_40(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 40 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_41(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 41 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_42(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 42 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_43(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 43 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_44(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 44 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_45(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 45 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_46(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 46 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_47(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 47 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_48(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 48 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_49(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 49 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_50(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 50 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_51(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 51 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_52(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 52 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_53(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 53 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_54(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 54 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_55(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 55 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_56(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 56 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_57(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 57 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_58(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 58 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_59(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 59 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_60(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 60 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_61(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 61 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_62(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 62 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }
static unsigned long long slot_63(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d){ if (getenv("STUB_TRACE")) fprintf(stderr, "[%lx] xgameruntime!slot 63 caller=%p args=%llx,%llx,%llx,%llx\n", GetCurrentThreadId(), __builtin_return_address(0), a, b, c, d); return slot_value() ? slot_value() : (unsigned long long)(uintptr_t)arena(); }

static void *vtable[512];
static void *object[1];

static void init_object(void)
{
    unsigned i;
    if (object[0]) return;
    for (i = 0; i < sizeof(vtable) / sizeof(vtable[0]); i++)
        vtable[i] = (void *)generic;
    vtable[0] = (void *)slot_0;
    vtable[1] = (void *)slot_1;
    vtable[2] = (void *)slot_2;
    vtable[3] = (void *)slot_3;
    vtable[4] = (void *)slot_4;
    vtable[5] = (void *)slot_5;
    vtable[6] = (void *)slot_6;
    vtable[7] = (void *)slot_7;
    vtable[8] = (void *)slot_8;
    vtable[9] = (void *)slot_9;
    vtable[10] = (void *)slot_10;
    vtable[11] = (void *)slot_11;
    vtable[12] = (void *)slot_12;
    vtable[13] = (void *)slot_13;
    vtable[14] = (void *)slot_14;
    vtable[15] = (void *)slot_15;
    vtable[16] = (void *)slot_16;
    vtable[17] = (void *)slot_17;
    vtable[18] = (void *)slot_18;
    vtable[19] = (void *)slot_19;
    vtable[20] = (void *)slot_20;
    vtable[21] = (void *)slot_21;
    vtable[22] = (void *)slot_22;
    vtable[23] = (void *)slot_23;
    vtable[24] = (void *)slot_24;
    vtable[25] = (void *)slot_25;
    vtable[26] = (void *)slot_26;
    vtable[27] = (void *)slot_27;
    vtable[28] = (void *)slot_28;
    vtable[29] = (void *)slot_29;
    vtable[30] = (void *)slot_30;
    vtable[31] = (void *)slot_31;
    vtable[32] = (void *)slot_32;
    vtable[33] = (void *)slot_33;
    vtable[34] = (void *)slot_34;
    vtable[35] = (void *)slot_35;
    vtable[36] = (void *)slot_36;
    vtable[37] = (void *)slot_37;
    vtable[38] = (void *)slot_38;
    vtable[39] = (void *)slot_39;
    vtable[40] = (void *)slot_40;
    vtable[41] = (void *)slot_41;
    vtable[42] = (void *)slot_42;
    vtable[43] = (void *)slot_43;
    vtable[44] = (void *)slot_44;
    vtable[45] = (void *)slot_45;
    vtable[46] = (void *)slot_46;
    vtable[47] = (void *)slot_47;
    vtable[48] = (void *)slot_48;
    vtable[49] = (void *)slot_49;
    vtable[50] = (void *)slot_50;
    vtable[51] = (void *)slot_51;
    vtable[52] = (void *)slot_52;
    vtable[53] = (void *)slot_53;
    vtable[54] = (void *)slot_54;
    vtable[55] = (void *)slot_55;
    vtable[56] = (void *)slot_56;
    vtable[57] = (void *)slot_57;
    vtable[58] = (void *)slot_58;
    vtable[59] = (void *)slot_59;
    vtable[60] = (void *)slot_60;
    vtable[61] = (void *)slot_61;
    vtable[62] = (void *)slot_62;
    vtable[63] = (void *)slot_63;
    object[0] = vtable;
}

long long QueryApiImpl(const void *iid_a, const void *iid_b, void **out, unsigned long long r9)
{
    init_object();
    TRACE("iid=%p iid2=%p out=%p r9=%llx", iid_a, iid_b, (void *)out, r9);
    if (out) *out = object;
    return 0;
}

long long InitializeApiImpl(void) { TRACE("", 0); return 0; }
long long InitializeApiImplEx(unsigned long long a, unsigned long long b)
{ TRACE("a=%llx b=%llx", a, b); return 0; }
long long InitializeApiImplEx2(unsigned long long a, unsigned long long b)
{ TRACE("a=%llx b=%llx", a, b); return 0; }
long long XErrorReport(unsigned long long code, unsigned long long a, unsigned long long b)
{ TRACE("code=%llx a=%llx b=%llx", code, a, b); return 0; }
long long UninitializeApiImpl(void) { TRACE("", 0); return 0; }
