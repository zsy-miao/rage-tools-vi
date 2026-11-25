/* XMem: the console memory allocator, expressed with VirtualAlloc.
 *
 * Signatures are inferred from call sites: the first call in this image is
 * XMemVirtualAlloc(0, 0x600000000, 0x20402000, 0x21), a 24 GiB reservation. Reserve and
 * commit succeed sparsely on 64-bit Windows, so the address space is not the limit.
 */
#include <windows.h>
#include <stdio.h>

static void *reserve(void *address, size_t size)
{
    void *p = VirtualAlloc(address, size, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (!p && address)
        p = VirtualAlloc(NULL, size, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (getenv("STUB_TRACE"))
        fprintf(stderr, "[%lx] xmem!alloc(%p, %llx) -> %p\n", GetCurrentThreadId(), address,
                (unsigned long long)size, p);
    return p;
}

void *XMemVirtualAlloc(void *address, size_t size, unsigned long long a, unsigned long long b)
{
    (void)a; (void)b;
    return reserve(address, size);
}

void *XMemAlloc(size_t size, unsigned long long alignment, unsigned long long flags)
{
    (void)alignment; (void)flags;
    return reserve(NULL, size);
}

void *XMemAllocDefault(size_t size, unsigned long long alignment)
{
    (void)alignment;
    return reserve(NULL, size);
}

unsigned long long XMemFree(void *p, size_t size, unsigned long long type)
{
    (void)size; (void)type;
    return VirtualFree(p, 0, MEM_RELEASE) ? 0 : 1;
}

unsigned long long XMemVirtualFree(void *p, size_t size, unsigned long long type)
{
    (void)size; (void)type;
    return VirtualFree(p, 0, MEM_RELEASE) ? 0 : 1;
}

void XMemFreeDefault(void *p) { VirtualFree(p, 0, MEM_RELEASE); }

/* "Tools memory" is the dev-kit scratch pool. Reporting it present is the shape a
 * development console reports; the image asking for it suggests a capability check. */
unsigned long long XMemIsToolsMemAvailable(void) { return 1; }

unsigned long long XMemGetWorkingSetStatistics(void *out, unsigned long long size)
{
    if (out && size) memset(out, 0, (size_t)size);
    return 0;
}

unsigned long long XMemAllocatePhysicalPages(void) { return 0; }
unsigned long long XMemFreePhysicalPages(void) { return 0; }
unsigned long long XMemMapPhysicalPages(void) { return 0; }
unsigned long long XMemMapPhysicalPagesScatter(void) { return 0; }
unsigned long long XMemTransferMemory(void) { return 0; }
