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
    note("d3d12_xs!D3D12ConfigureVirtualMemoryX(%p, %llx, %x, %x) -> S_OK",
         base, size, alignment, flags);
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

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved)
{
    (void)instance;
    (void)reason;
    (void)reserved;
    return TRUE;
}
