/* GameInput: the image imports ordinal 1 only, and calls it as `GameInputCreate(out)`.
 * FUN_1459258a0 caches the result and uses vtable slot +0x10 on it. The object answers
 * every slot with a zero return so the caller can continue.
 */
#include <windows.h>
#include <stdio.h>

static unsigned long long generic(void)
{
    if (getenv("STUB_TRACE"))
        fprintf(stderr, "[%lx] %s!method caller=%p\n", GetCurrentThreadId(),
                "gameinput", __builtin_return_address(0));
    return 0;
}
BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID reserved)
{
    (void)module; (void)reserved;
    if (reason == DLL_PROCESS_ATTACH && getenv("STUB_TRACE"))
        fprintf(stderr, "gameinput!loaded\n");
    return TRUE;
}

static void *vtable[512];
static void *object[1];

/* The image caches the interface in a global and releases it during teardown; when the
 * global is still null the release dereferences null at image+0x5925903. Seeding the
 * global with our object keeps teardown consistent with what the game would see after a
 * successful create. */
static void seed_global(void)
{
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    void **slot;
    if (!base) return;
    slot = (void **)(base + 0x9AB15E8);
    if (object[0]) *slot = object[0];
    if (getenv("STUB_TRACE"))
        fprintf(stderr, "gameinput!seed global %p = %p\n", (void *)slot, *slot);
}

long long ord_1(void **out, unsigned long long flags)
{
    unsigned i;
    if (!object[0]) {
        for (i = 0; i < sizeof(vtable) / sizeof(vtable[0]); i++)
            vtable[i] = (void *)generic;
        object[0] = vtable;
    }
    if (getenv("STUB_TRACE"))
        fprintf(stderr, "[%lx] gameinput!ord_1(out=%p flags=%llx)\n",
                GetCurrentThreadId(), (void *)out, flags);
    if (out) *out = object;
    return 0;
}
