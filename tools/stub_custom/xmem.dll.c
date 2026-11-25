/* XMem: the console memory allocator, expressed with VirtualAlloc.
 *
 * Signatures are inferred from call sites: the first call in this image is
 * XMemVirtualAlloc(0, 0x600000000, 0x20402000, 0x21), a 24 GiB reservation. Reserve and
 * commit succeed sparsely on 64-bit Windows, so the address space is not the limit.
 */
#include <windows.h>
#include <stdio.h>

/* The console reserves much more than it touches: this image asks for 24 GiB before it
 * creates a device. Committing that much fails, and Wine then relocates the request, which
 * breaks the title's GPU address arithmetic. Reserve only above 1 GiB and commit on touch, so
 * the reservation keeps the address the title asked for and stays sparse like the console's. */
#define COMMIT_ON_TOUCH_LIMIT (1024ull * 1024 * 1024)

/* Ranges we reserved but did not commit. The touch handler must only commit inside them:
 * intercepting every access violation (including the CRT heap's guard-page probes) breaks the
 * heap's own growth and turns every later allocation into NULL. */
#define TRACKED_RANGES 32
static struct { uintptr_t begin, end; } g_ranges[TRACKED_RANGES];
static volatile LONG g_range_count;

static void track(void *base, size_t size, int reserved_only)
{
    LONG index;
    if (!reserved_only || base == NULL || size == 0)
        return;
    index = InterlockedIncrement(&g_range_count) - 1;
    if (index < TRACKED_RANGES)
    {
        g_ranges[index].begin = (uintptr_t)base;
        g_ranges[index].end = (uintptr_t)base + size;
    }
}

static void *reserve(void *address, size_t size)
{
    DWORD flags = MEM_RESERVE | MEM_COMMIT;
    void *p;
    {
        /* Experiment knob: cap what is actually reserved, to see whether the title's own
         * allocator fails because the address space is already taken by these reservations. */
        const char *cap = getenv("STUB_XMEM_CAP");
        if (cap != NULL)
        {
            unsigned long long limit = strtoull(cap, NULL, 0);
            if (limit != 0 && size > (size_t)limit)
                size = (size_t)limit;
        }
    }
    if (size > COMMIT_ON_TOUCH_LIMIT)
        flags = MEM_RESERVE;
    p = VirtualAlloc(address, size, flags, PAGE_READWRITE);
    if (!p && address)
        p = VirtualAlloc(NULL, size, flags, PAGE_READWRITE);
    track(p, size, flags == MEM_RESERVE);
    if (getenv("STUB_TRACE"))
        fprintf(stderr, "[%lx] xmem!alloc(%p, %llx, %s) -> %p\n", GetCurrentThreadId(), address,
                (unsigned long long)size, flags == MEM_RESERVE ? "reserve" : "commit", p);
    return p;
}

/* Committing on touch: the title writes anywhere in a reservation and expects memory. */
static LONG WINAPI commit_on_touch(EXCEPTION_POINTERS *info)
{
    void *fault = (void *)info->ExceptionRecord->ExceptionInformation[1];
    void *page = (void *)((uintptr_t)fault & ~(uintptr_t)0xfff);
    if (info->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION || fault == NULL)
        return EXCEPTION_CONTINUE_SEARCH;
    {
        LONG index;
        int inside = 0;
        for (index = 0; index < g_range_count && index < TRACKED_RANGES; index++)
            if ((uintptr_t)fault >= g_ranges[index].begin &&
                (uintptr_t)fault < g_ranges[index].end)
                inside = 1;
        if (!inside)
            return EXCEPTION_CONTINUE_SEARCH;
    }
    if (VirtualAlloc(page, 0x1000, MEM_COMMIT, PAGE_READWRITE) == NULL)
        return EXCEPTION_CONTINUE_SEARCH;
    return EXCEPTION_CONTINUE_EXECUTION;
}

static void install_touch_handler(void)
{
    static int installed;
    if (installed)
        return;
    AddVectoredExceptionHandler(1, commit_on_touch);
    installed = 1;
}

void *XMemVirtualAlloc(void *address, size_t size, unsigned long long a, unsigned long long b)
{
    (void)a; (void)b;
    install_touch_handler();
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
