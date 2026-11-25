/* XCRDAPI: imported for DStorageGetFactory only.
 *
 * The image calls it early, sometimes with a null out parameter (a capability probe), and
 * then uses the factory it gets back through its vtable. DirectStorage's object model is
 * COM-shaped, so the stub hands back an object whose slots are numbered: the call order and
 * the arguments say which methods the image needs, and what to implement first.
 *
 * STUB_TRACE=1 prints the requested IID and every slot call with its arguments.
 */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

#define TRACE(...) do { if (getenv("STUB_TRACE")) { fprintf(stderr, "[%lx] xcrdapi! ", \
    GetCurrentThreadId()); fprintf(stderr, __VA_ARGS__); fprintf(stderr, "\n"); } } while (0)

static unsigned char g_arena[0x2000];

/* A slot that returns a pointer must not return 0: the camera path copies from it without a
 * null check (measured on the GDK side). A zeroed arena is the least this stub can say. */
#define SLOT(n) \
    static unsigned long long slot_##n(unsigned long long a, unsigned long long b, \
                                       unsigned long long c, unsigned long long d) \
    { TRACE("slot %d caller=%p args=%llx,%llx,%llx,%llx", n, __builtin_return_address(0), \
            a, b, c, d); return 0; }

SLOT(0) SLOT(1) SLOT(2) SLOT(3) SLOT(4) SLOT(5) SLOT(6) SLOT(7)
SLOT(8) SLOT(9) SLOT(10) SLOT(11) SLOT(12) SLOT(13) SLOT(14) SLOT(15)
SLOT(16) SLOT(17) SLOT(18) SLOT(19) SLOT(20) SLOT(21) SLOT(22) SLOT(23)

static void *vtable[512];
static void *object[1];

/* The object the caller receives is an address whose first qword is the vtable: the image
 * does `mov rax, [object]` then `call *0x40(%rax)`. Handing back the vtable itself makes that
 * read index into code bytes (measured: a read of address -1). */
static void *build(void)
{
    unsigned i;
    if (object[0])
        return object[0];
    for (i = 0; i < sizeof(vtable) / sizeof(vtable[0]); i++)
        vtable[i] = (void *)slot_0;
#define SET(n) vtable[n] = (void *)slot_##n
    SET(0); SET(1); SET(2); SET(3); SET(4); SET(5); SET(6); SET(7);
    SET(8); SET(9); SET(10); SET(11); SET(12); SET(13); SET(14); SET(15);
    SET(16); SET(17); SET(18); SET(19); SET(20); SET(21); SET(22); SET(23);
#undef SET
    object[0] = vtable;
    return object;
}

long long DStorageGetFactory(const void *iid, void **out, unsigned long long c,
                             unsigned long long d)
{
    const unsigned char *bytes = (const unsigned char *)iid;
    if (getenv("STUB_TRACE")) {
        TRACE("DStorageGetFactory(iid=%p out=%p c=%llx d=%llx)", iid, (void *)out, c, d);
        if (bytes)
            TRACE("  iid bytes %02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
                  bytes[3], bytes[2], bytes[1], bytes[0], bytes[5], bytes[4], bytes[7],
                  bytes[6], bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13],
                  bytes[14], bytes[15]);
    }
    if (out)
        *out = build();
    return 0;
}
