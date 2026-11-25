/* XCRDAPI: imported for DStorageGetFactory only.
 * The abort at game.exe+0x1D8E505 happens immediately after it returns, with the factory
 * slot still null, so the call is `DStorageGetFactory(iid, &factory)` and the caller
 * asserts on the result. Answer with a vtable-backed object that returns zero.
 */
#include <windows.h>
#include <stdio.h>

static unsigned long long generic(void)
{
    if (getenv("STUB_TRACE"))
        fprintf(stderr, "[%lx] %s!method caller=%p\n", GetCurrentThreadId(),
                "xcrdapi", __builtin_return_address(0));
    return 0;
}
static void *vtable[512];
static void *object[1];

long long DStorageGetFactory(const void *iid, void **out, unsigned long long c, unsigned long long d)
{
    unsigned i;
    if (!object[0]) {
        for (i = 0; i < sizeof(vtable) / sizeof(vtable[0]); i++)
            vtable[i] = (void *)generic;
        object[0] = vtable;
    }
    if (getenv("STUB_TRACE"))
        fprintf(stderr, "[%lx] xcrdapi!DStorageGetFactory(iid=%p out=%p c=%llx d=%llx)\n",
                iid, (void *)out, c, d);
    if (out) *out = object;
    return 0;
}
