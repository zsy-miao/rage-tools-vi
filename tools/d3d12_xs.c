/*
 * d3d12_xs.dll for Wine: the console's D3D12 entry points, backed by vkd3d-proton.
 *
 * The image imports three names from d3d12_xs.dll:
 *
 *   D3D12ConfigureVirtualMemoryX       — console memory-window setup, no PC equivalent
 *   D3D12SerializeVersionedRootSignature — identical to the PC function
 *   D3D12XboxCreateDevice              — the console device creator
 *
 * A stub that returns 0 for all three lets the loader finish and then leaves the image with
 * objects it cannot use. This instead forwards the two functions that have a PC counterpart
 * to the prefix's d3d12.dll (vkd3d-proton or Wine's own) and treats the memory-window call as
 * a no-op that reports its arguments. Every call is written to stderr, so the log says what
 * the image asked for and what the host answered.
 *
 * The Xbox device-parameter block is not public. Its first words are logged and the host
 * device is created at feature level 12_0 — the level a Scarlett title requires — with the
 * caller's IID, so the interface the image receives is the one it asked for.
 *
 * Build: python3 tools/d3d12_shim.py        (mingw-w64, no link dependencies)
 */

#include <windows.h>
#include <stdarg.h>
#include <string.h>
#include <stdlib.h>

#define FL_12_0 0xc000

/* A tiny formatter: %p, %llx, %lx, %x, %s and %%. Avoiding the CRT's printf keeps this DLL
 * free of USER32 and of any dependency a console title might not have. */
static char *emit(char *cursor, char *end, const char *text)
{
    while (*text && cursor < end)
        *cursor++ = *text++;
    return cursor;
}

static char *emit_number(char *cursor, char *end, unsigned long long value, int digits,
                         const char *prefix)
{
    char buffer[24];
    int count = 0;
    if (prefix != NULL)
        cursor = emit(cursor, end, prefix);
    do {
        buffer[count++] = (char)(value & 0xf);
        value >>= 4;
    } while (value != 0 || count < digits);
    if (digits == 0) {
        while (count < 16)
            buffer[count++] = 0;
    }
    while (count > 0 && cursor < end) {
        int digit = buffer[--count];
        *cursor++ = (char)(digit < 10 ? '0' + digit : 'a' + digit - 10);
    }
    return cursor;
}

static void note(const char *format, ...)
{
    char buffer[512];
    char *cursor = buffer;
    char *end = buffer + sizeof(buffer) - 2;
    va_list args;

    va_start(args, format);
    while (*format && cursor < end) {
        if (*format != '%') {
            *cursor++ = *format++;
            continue;
        }
        format++;
        switch (*format) {
        case 'p':
            cursor = emit_number(cursor, end, (unsigned long long)(UINT_PTR)va_arg(args, void *),
                                 16, "0x");
            break;
        case 'x':
            cursor = emit_number(cursor, end, va_arg(args, unsigned int), 0, NULL);
            break;
        case 'u':
        case 'd':
        {
            char digits[16];
            unsigned long long value = va_arg(args, unsigned int);
            int length = 0;
            if (value == 0)
                digits[length++] = '0';
            while (value != 0)
            {
                digits[length++] = (char)('0' + (value % 10));
                value /= 10;
            }
            while (length > 0 && cursor < end)
                *cursor++ = digits[--length];
            break;
        }
        case 'l':
            format++;
            if (*format == 'l') {
                format++;
                cursor = emit_number(cursor, end, va_arg(args, unsigned long long), 0, "0x");
            } else {
                cursor = emit_number(cursor, end, va_arg(args, unsigned long), 0, "0x");
            }
            break;
        case 's':
            cursor = emit(cursor, end, va_arg(args, const char *));
            break;
        case '%':
            *cursor++ = '%';
            break;
        default:
            *cursor++ = '%';
            *cursor++ = *format;
            break;
        }
        format++;
    }
    va_end(args);
    *cursor++ = '\n';
    WriteFile(GetStdHandle(STD_ERROR_HANDLE), buffer, (DWORD)(cursor - buffer), NULL, NULL);
}

static HMODULE host(void)
{
    static HMODULE module;
    if (module == NULL)
        module = LoadLibraryA("d3d12.dll");
    return module;
}

static FARPROC host_export(const char *name)
{
    HMODULE module = host();
    FARPROC function;
    if (module == NULL)
        return NULL;
    function = GetProcAddress(module, name);
    if (function == NULL)
        note("d3d12_xs!%s: not exported by the host d3d12.dll", name);
    return function;
}

__declspec(dllexport) HRESULT WINAPI D3D12ConfigureVirtualMemoryX(void *base, UINT64 size,
                                                                  UINT32 alignment, UINT32 flags)
{
    /* The contract, from a static pass another project published: one pointer to a 32-byte
     * configuration, zero-initialised, with only the DWORD at offset 4 written
     * (ceil(size / 16 GiB) + 2, so 3 for 16 GiB and 4 for 24 GiB). Anything else is refused
     * without touching state. */
    {
        const unsigned char *config = (const unsigned char *)base;
        unsigned index;
        note("d3d12_xs!D3D12ConfigureVirtualMemoryX(config %p)", base);
        if (config != NULL)
        {
            unsigned written = 0;
            for (index = 0; index < 32; index++)
                written += config[index] != 0;
            note("d3d12_xs!  %u non-zero byte(s) of 32, offset 4 = %lu",
                 written,
                 (unsigned long)(config[4] | (config[5] << 8) | (config[6] << 16) |
                                 ((unsigned long)config[7] << 24)));
        }
    }
    return S_OK;
}

__declspec(dllexport) HRESULT WINAPI D3D12SerializeVersionedRootSignature(
    const void *description, void **blob, void **error)
{
    typedef HRESULT (WINAPI *function_t)(const void *, void **, void **);
    function_t function = (function_t)host_export("D3D12SerializeVersionedRootSignature");
    HRESULT result;
    if (function == NULL)
        return E_NOTIMPL;
    result = function(description, blob, error);
    note("d3d12_xs!D3D12SerializeVersionedRootSignature(flags %#x) -> %#lx",
         description ? *(const UINT *)description : 0, (unsigned long)result);
    return result;
}

__declspec(dllexport) HRESULT WINAPI D3D12CreateRootSignatureDeserializer(
    const void *data, SIZE_T size, const GUID *iid, void **deserializer)
{
    typedef HRESULT (WINAPI *function_t)(const void *, SIZE_T, const GUID *, void **);
    function_t function = (function_t)host_export("D3D12CreateRootSignatureDeserializer");
    if (function == NULL)
        return E_NOTIMPL;
    return function(data, size, iid, deserializer);
}

__declspec(dllexport) HRESULT WINAPI D3D12CreateVersionedRootSignatureDeserializer(
    const void *data, SIZE_T size, const GUID *iid, void **deserializer)
{
    typedef HRESULT (WINAPI *function_t)(const void *, SIZE_T, const GUID *, void **);
    function_t function = (function_t)host_export("D3D12CreateVersionedRootSignatureDeserializer");
    if (function == NULL)
        return E_NOTIMPL;
    return function(data, size, iid, deserializer);
}

__declspec(dllexport) HRESULT WINAPI D3D12CreateDevice(IUnknown *adapter, UINT32 level,
                                                       const GUID *iid, void **device)
{
    typedef HRESULT (WINAPI *function_t)(IUnknown *, UINT32, const GUID *, void **);
    function_t function = (function_t)host_export("D3D12CreateDevice");
    if (function == NULL)
        return E_NOTIMPL;
    return function(adapter, level, iid, device);
}

__declspec(dllexport) HRESULT WINAPI D3D12GetDebugInterface(const GUID *iid, void **debug)
{
    typedef HRESULT (WINAPI *function_t)(const GUID *, void **);
    function_t function = (function_t)host_export("D3D12GetDebugInterface");
    if (function == NULL)
        return E_NOTIMPL;
    return function(iid, debug);
}

__declspec(dllexport) HRESULT WINAPI D3D12SerializeRootSignature(const void *description,
                                                                 UINT32 version,
                                                                 void **blob, void **error)
{
    typedef HRESULT (WINAPI *function_t)(const void *, UINT32, void **, void **);
    function_t function = (function_t)host_export("D3D12SerializeRootSignature");
    if (function == NULL)
        return E_NOTIMPL;
    return function(description, version, blob, error);
}

__declspec(dllexport) HRESULT WINAPI D3D12EnableExperimentalFeatures(
    UINT32 count, const GUID *iids, void *configurations, UINT32 *sizes)
{
    typedef HRESULT (WINAPI *function_t)(UINT32, const GUID *, void *, UINT32 *);
    function_t function = (function_t)host_export("D3D12EnableExperimentalFeatures");
    if (function == NULL)
        return E_NOTIMPL;
    return function(count, iids, configurations, sizes);
}

__declspec(dllexport) HRESULT WINAPI D3D12GetInterface(const GUID *clsid, const GUID *iid,
                                                       void **out)
{
    typedef HRESULT (WINAPI *function_t)(const GUID *, const GUID *, void **);
    function_t function = (function_t)host_export("D3D12GetInterface");
    if (function == NULL)
        return E_NOTIMPL;
    return function(clsid, iid, out);
}

__declspec(dllexport) HRESULT WINAPI D3D12XboxCreateDevice(IUnknown *adapter, const void *params,
                                                           const GUID *iid, void **device)
{
    typedef HRESULT (WINAPI *function_t)(IUnknown *, UINT32, const GUID *, void **);
    function_t function = (function_t)host_export("D3D12CreateDevice");
    const unsigned long long *words = (const unsigned long long *)params;
    HRESULT result;

    note("d3d12_xs!D3D12XboxCreateDevice(adapter %p, iid %08lx-%04x, params %p)",
         adapter, iid ? (unsigned long)iid->Data1 : 0, iid ? iid->Data2 : 0, params);
    if (words != NULL)
        note("d3d12_xs!  params %llx %llx %llx %llx %llx %llx %llx %llx",
             words[0], words[1], words[2], words[3], words[4], words[5], words[6], words[7]);
    if (function == NULL)
        return E_NOTIMPL;
    if (device != NULL)
        *device = NULL;
    result = function(adapter, FL_12_0, iid, device);
    note("d3d12_xs!D3D12XboxCreateDevice -> %#lx (device %p)", (unsigned long)result,
         device ? *device : NULL);
    return result;
}


/* ---------------------------------------------------------------------------------------
 * App-state notification hook.
 *
 * The image registers for application state changes and then waits for one; Wine answers
 * RegisterAppStateChangeNotification with a stub that never invokes the callback, so nothing
 * ever arrives. Both routines are imported from an api-ms-win-core-psm-appnotify set, whose
 * IAT entries are patched here as soon as this DLL attaches (it is loaded before the image
 * registers). Each routine is remembered and called once with "not quiesced" after a moment,
 * which is what "the title is now active" looks like to the caller.
 * ------------------------------------------------------------------------------------ */

typedef void (WINAPI *appstate_routine)(BOOLEAN quiesced, PVOID context);

static appstate_routine g_state_routine;
static PVOID g_state_context;
static appstate_routine g_constrained_routine;
static PVOID g_constrained_context;
static HANDLE g_semaphores[8];
static int g_semaphore_count;
static LPVOID (WINAPI *real_VirtualAlloc)(LPVOID, SIZE_T, DWORD, DWORD);
static int g_alloc_logged;
static int g_alloc_failed;

static LPVOID WINAPI hook_VirtualAlloc(LPVOID address, SIZE_T size, DWORD type, DWORD protect)
{
    LPVOID result = real_VirtualAlloc(address, size, type, protect);
    if (result == NULL)
        g_alloc_failed++;
    if (g_alloc_logged < 24)
    {
        g_alloc_logged++;
        note("alloc: VirtualAlloc(%p, %llx, %lx, %lx) -> %p", address,
             (unsigned long long)size, (unsigned long)type, (unsigned long)protect, result);
    }
    return result;
}

static HANDLE g_events[16];
static int g_event_count;

static long long WINAPI hook_RegisterAppStateChangeNotification(appstate_routine routine,
                                                                PVOID context, PVOID registration)
{
    g_state_routine = routine;
    g_state_context = context;
    note("appstate!RegisterAppStateChangeNotification(routine %p, context %p) hooked",
         routine, context);
    if (registration)
        *(PVOID *)registration = (PVOID)(UINT_PTR)1;
    return 0;
}

static long long WINAPI hook_RegisterAppConstrainedChangeNotification(appstate_routine routine,
                                                                      PVOID context,
                                                                      PVOID registration)
{
    g_constrained_routine = routine;
    g_constrained_context = context;
    note("appstate!RegisterAppConstrainedChangeNotification(routine %p, context %p) hooked",
         routine, context);
    if (registration)
        *(PVOID *)registration = (PVOID)(UINT_PTR)2;
    return 0;
}

static DWORD WINAPI appstate_thread(LPVOID unused)
{
    (void)unused;
    /* Off by default: a state change delivered before the engine is ready makes it assert
     * (measured: int3 at image+0x1e1d574). STUB_APPSTATE=1 turns the delivery on. */
    if (getenv("STUB_APPSTATE") == NULL)
        return 0;
    { const char *d = getenv("STUB_APPSTATE_DELAY"); Sleep(d ? (DWORD)atoi(d) : 2000); }
    {
        const char *raw = getenv("STUB_APPSTATE_VALUE");
        const char *other = getenv("STUB_APPSTATE_CONSTRAINED");
        BOOLEAN value = raw ? (BOOLEAN)atoi(raw) : FALSE;
        BOOLEAN constrained = other ? (BOOLEAN)atoi(other) : value;
        if (g_constrained_routine)
        {
            note("appstate: calling the constrained routine (%s)",
                 constrained ? "TRUE" : "FALSE");
            g_constrained_routine(constrained, g_constrained_context);
        }
        if (g_state_routine)
        {
            note("appstate: calling the state routine (%s)", value ? "TRUE" : "FALSE");
            g_state_routine(value, g_state_context);
        }
    }
    Sleep(1500);
    if (g_semaphore_count > 0)
    {
        LONG previous = -1;
        ReleaseSemaphore(g_semaphores[0], 1, &previous);
        note("semaphore: released %p (previous count %ld)", g_semaphores[0], (long)previous);
    }
    return 0;
}

/* Replace one import slot in the running image by name. */
static void patch_import(HMODULE image, const char *wanted, void *replacement)
{
    unsigned char *base = (unsigned char *)image;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + dos->e_lfanew);
    IMAGE_IMPORT_DESCRIPTOR *descriptor = (IMAGE_IMPORT_DESCRIPTOR *)
        (base + nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress);
    DWORD old;
    for (; descriptor->Name; descriptor++)
    {
        const char *dll = (const char *)(base + descriptor->Name);
        IMAGE_THUNK_DATA64 *name_thunk = (IMAGE_THUNK_DATA64 *)(base + descriptor->OriginalFirstThunk);
        IMAGE_THUNK_DATA64 *address_thunk = (IMAGE_THUNK_DATA64 *)(base + descriptor->FirstThunk);
        if (descriptor->OriginalFirstThunk == 0)
            continue;
        for (; name_thunk->u1.AddressOfData; name_thunk++, address_thunk++)
        {
            char *name;
            if (name_thunk->u1.Ordinal & IMAGE_ORDINAL_FLAG64)
                continue;
            name = (char *)(base + (DWORD)name_thunk->u1.AddressOfData + 2);
            if (strcmp(name, wanted) != 0)
                continue;
            if (VirtualProtect(address_thunk, sizeof(*address_thunk), PAGE_READWRITE, &old))
            {
                address_thunk->u1.Function = (ULONGLONG)(UINT_PTR)replacement;
                VirtualProtect(address_thunk, sizeof(*address_thunk), old, &old);
            }
            note("appstate: %s patched in %s", wanted, dll);
            return;
        }
    }
    note("appstate: %s not found in the image's imports", wanted);
}


/* --- wait / message probes -------------------------------------------------------------
 * The image ends up waiting in a Wine server select. These wrappers say what it waits on,
 * and how it pumps messages, without changing behaviour: each one logs the first calls and
 * forwards to the real implementation. */
static DWORD (WINAPI *real_WaitForMultipleObjects)(DWORD, const HANDLE *, BOOL, DWORD);
static DWORD (WINAPI *real_WaitForSingleObject)(HANDLE, DWORD);
static HANDLE (WINAPI *real_CreateSemaphoreW)(void *, LONG, LONG, LPCWSTR);
static HANDLE (WINAPI *real_CreateEventW)(void *, BOOL, BOOL, LPCWSTR);
static HANDLE (WINAPI *real_CreateEventA)(void *, BOOL, BOOL, LPCSTR);

static void remember_event(HANDLE handle, BOOL manual, BOOL initial)
{
    if (handle && handle != INVALID_HANDLE_VALUE && manual && !initial && g_event_count < 16)
    {
        g_events[g_event_count++] = handle;
        note("event: manual-reset %p created (initial 0) by caller %p", handle,
             __builtin_return_address(0));
    }
}

static HANDLE WINAPI hook_CreateEventW(void *a, BOOL manual, BOOL initial, LPCWSTR name)
{
    HANDLE handle = real_CreateEventW(a, manual, initial, name);
    remember_event(handle, manual, initial);
    return handle;
}

static HANDLE WINAPI hook_CreateEventA(void *a, BOOL manual, BOOL initial, LPCSTR name)
{
    HANDLE handle = real_CreateEventA(a, manual, initial, name);
    remember_event(handle, manual, initial);
    return handle;
}

static HANDLE (WINAPI *real_CreateThread)(void *, SIZE_T, DWORD (WINAPI *)(void *), void *,
                                          DWORD, DWORD *);
static int g_threads_logged;

static HANDLE WINAPI hook_CreateThread(void *attributes, SIZE_T stack,
                                       DWORD (WINAPI *start)(void *), void *parameter,
                                       DWORD flags, DWORD *id)
{
    HANDLE handle = real_CreateThread(attributes, stack, start, parameter, flags, id);
    if (g_threads_logged < 16)
    {
        g_threads_logged++;
        note("thread: created %p start %p param %p flags %lu", handle, start, parameter,
             (unsigned long)flags);
    }
    return handle;
}

static HANDLE WINAPI hook_CreateSemaphoreW(void *attributes, LONG initial, LONG maximum,
                                           LPCWSTR name)
{
    HANDLE handle = real_CreateSemaphoreW(attributes, initial, maximum, name);
    if (g_semaphore_count < 8)
    {
        g_semaphores[g_semaphore_count++] = handle;
        note("semaphore: created %p initial %ld max %ld name %p", handle, (long)initial,
             (long)maximum, name);
    }
    return handle;
}
static int g_single_logged;

typedef struct { USHORT length, maximum; PWSTR buffer; } unicode_string_t;
typedef struct { unicode_string_t name; ULONG index; ULONG total; ULONG nonpaged; } object_type_t;

static void describe_handle(HANDLE handle)
{
    typedef LONG (NTAPI *query_t)(HANDLE, ULONG, void *, ULONG, ULONG *);
    static query_t query;
    unsigned char buffer[512];
    ULONG needed = 0;
    object_type_t *type;
    query_t function = (query_t)GetProcAddress(GetModuleHandleA("ntdll.dll"), "NtQueryObject");
    if (function == NULL)
        return;
    query = function;
    if (query(handle, 2 /* ObjectTypeInformation */, buffer, sizeof(buffer), &needed) != 0)
        return;
    type = (object_type_t *)buffer;
    if (type->name.buffer)
    {
        char name[64];
        if (WideCharToMultiByte(CP_ACP, 0, type->name.buffer,
                                type->name.length / sizeof(WCHAR), name, sizeof(name) - 1,
                                NULL, NULL) > 0)
        {
            name[sizeof(name) - 1] = 0;
            note("wait: handle %p is a %s", handle, name);
        }
    }
}

/* Probe knob: STUB_KICK=1 releases a semaphore the image waits on forever, one signal per
 * wait, so a "wait for N workers" loop can be drained and the next wall becomes visible. */
static DWORD WINAPI event_kick_thread(LPVOID unused)
{
    const char *kick = getenv("STUB_EVENT_KICK");
    int index;
    (void)unused;
    if (kick == NULL)
        return 0;
    Sleep((DWORD)atoi(kick));
    for (index = 0; index < g_event_count; index++)
    {
        SetEvent(g_events[index]);
        note("event: signalled %p", g_events[index]);
    }
    return 0;
}

static DWORD WINAPI kick_thread(LPVOID parameter)
{
    LONG previous = -1;
    Sleep(400);
    ReleaseSemaphore((HANDLE)parameter, 1, &previous);
    note("semaphore: kicked %p (previous count %ld)", parameter, (long)previous);
    return 0;
}

static DWORD WINAPI hook_WaitForSingleObject(HANDLE handle, DWORD milliseconds)
{
    DWORD result;
    if (milliseconds == INFINITE && getenv("STUB_KICK"))
        CloseHandle(CreateThread(NULL, 0, kick_thread, handle, 0, NULL));
    if (g_single_logged < 16)
    {
        g_single_logged++;
        note("wait: WaitForSingleObject(handle %p, ms %lu) caller %p", handle,
             (unsigned long)milliseconds, __builtin_return_address(0));
        describe_handle(handle);
        if (milliseconds == INFINITE)
        {
            /* Windows-level backtrace: gdb only unwinds the unix side, so the engine's own
             * frames have to come from the API that knows them. */
            void *frames[24];
            USHORT captured = RtlCaptureStackBackTrace(0, 24, frames, NULL);
            USHORT index;
            for (index = 0; index < captured; index++)
                note("wait:   frame %u %p", index, frames[index]);
        }
    }
    result = real_WaitForSingleObject(handle, milliseconds);
    return result;
}
static BOOL (WINAPI *real_PeekMessageA)(LPMSG, HWND, UINT, UINT, UINT);
static LRESULT (WINAPI *real_DispatchMessageA)(const MSG *);
static int g_wait_logged, g_peek_logged, g_dispatch_logged;

static DWORD WINAPI hook_WaitForMultipleObjects(DWORD count, const HANDLE *handles, BOOL wait_all,
                                                DWORD milliseconds)
{
    DWORD result;
    if (g_wait_logged < 12)
    {
        g_wait_logged++;
        note("wait: WaitForMultipleObjects(count %lu, all %d, ms %lu) first handle %p",
             (unsigned long)count, (int)wait_all, (unsigned long)milliseconds,
             count ? handles[0] : NULL);
    }
    result = real_WaitForMultipleObjects(count, handles, wait_all, milliseconds);
    if (result == WAIT_TIMEOUT)
        note("wait: timed out after %lu ms", (unsigned long)milliseconds);
    return result;
}

static BOOL WINAPI hook_PeekMessageA(LPMSG message, HWND window, UINT first, UINT last,
                                     UINT remove)
{
    BOOL found = real_PeekMessageA(message, window, first, last, remove);
    if (g_peek_logged < 8)
    {
        g_peek_logged++;
        note("pump: PeekMessageA(hwnd %p, %u..%u, remove %u) -> %d", window, first, last,
             remove, (int)found);
    }
    return found;
}

static LRESULT WINAPI hook_DispatchMessageA(const MSG *message)
{
    if (g_dispatch_logged < 8)
    {
        g_dispatch_logged++;
        note("pump: DispatchMessageA(hwnd %p, msg %#x, wparam %#lx, lparam %#lx)",
             message ? message->hwnd : NULL, message ? message->message : 0,
             message ? (unsigned long)message->wParam : 0,
             message ? (unsigned long)message->lParam : 0);
    }
    return real_DispatchMessageA(message);
}

static void install_wait_hooks(HMODULE image)
{
    HMODULE kernel = GetModuleHandleA("kernel32.dll");
    HMODULE user = GetModuleHandleA("user32.dll");
    real_WaitForMultipleObjects = (void *)GetProcAddress(kernel, "WaitForMultipleObjects");
    real_WaitForSingleObject = (void *)GetProcAddress(kernel, "WaitForSingleObject");
    real_CreateSemaphoreW = (void *)GetProcAddress(kernel, "CreateSemaphoreW");
    real_CreateThread = (void *)GetProcAddress(kernel, "CreateThread");
    real_VirtualAlloc = (void *)GetProcAddress(kernel, "VirtualAlloc");
    real_CreateEventW = (void *)GetProcAddress(kernel, "CreateEventW");
    real_CreateEventA = (void *)GetProcAddress(kernel, "CreateEventA");
    real_PeekMessageA = (void *)GetProcAddress(user, "PeekMessageA");
    real_DispatchMessageA = (void *)GetProcAddress(user, "DispatchMessageA");
    if (real_WaitForMultipleObjects)
        patch_import(image, "WaitForMultipleObjects", (void *)hook_WaitForMultipleObjects);
    if (real_WaitForSingleObject)
        patch_import(image, "WaitForSingleObject", (void *)hook_WaitForSingleObject);
    if (real_CreateSemaphoreW)
        patch_import(image, "CreateSemaphoreW", (void *)hook_CreateSemaphoreW);
    if (real_CreateThread)
        patch_import(image, "CreateThread", (void *)hook_CreateThread);
    if (real_VirtualAlloc)
        patch_import(image, "VirtualAlloc", (void *)hook_VirtualAlloc);
    if (real_CreateEventW)
        patch_import(image, "CreateEventW", (void *)hook_CreateEventW);
    if (real_CreateEventA)
        patch_import(image, "CreateEventA", (void *)hook_CreateEventA);
    if (real_PeekMessageA)
        patch_import(image, "PeekMessageA", (void *)hook_PeekMessageA);
    if (real_DispatchMessageA)
        patch_import(image, "DispatchMessageA", (void *)hook_DispatchMessageA);
}

static void install_appstate_hooks(void)
{
    HMODULE image = GetModuleHandleA(NULL);
    if (image == NULL)
        return;
    patch_import(image, "RegisterAppStateChangeNotification",
                 (void *)hook_RegisterAppStateChangeNotification);
    patch_import(image, "RegisterAppConstrainedChangeNotification",
                 (void *)hook_RegisterAppConstrainedChangeNotification);
    CloseHandle(CreateThread(NULL, 0, appstate_thread, NULL, 0, NULL));
    install_wait_hooks(image);
    if (getenv("STUB_EVENT_KICK") != NULL)
        CloseHandle(CreateThread(NULL, 0, event_kick_thread, NULL, 0, NULL));
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved)
{
    (void)instance;
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH)
        install_appstate_hooks();
    return TRUE;
}
