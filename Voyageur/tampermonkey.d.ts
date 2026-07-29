// Ambient type declarations for the Tampermonkey APIs Archivist.js uses (declared via
// @grant in its userscript header). These give the IDE real type information for
// `unsafeWindow`/`GM_xmlhttpRequest` instead of flagging them as unresolved globals -
// this file is never imported, it's picked up automatically as project-wide ambient types.

declare const unsafeWindow: Window & typeof globalThis;

// Custom properties Archivist.js reads/writes on the page's own window object: its
// network-interception cache (__mgs_*) and Ancestry's own React state blob
// (__PRELOADED_STATE__, an arbitrary/undocumented shape - typed as `any` since it's
// entirely Ancestry's internal data, not something this script controls or can predict).
interface Window {
    __mgs_intercepted?: boolean;
    __mgs_pids?: string[];
    __PRELOADED_STATE__?: any;
}

interface GMXmlHttpRequestResponse {
    status: number;
    responseText: string;
    response: any;
    [key: string]: any;
}

interface GMXmlHttpRequestDetails {
    method: string;
    url: string;
    responseType?: string;
    timeout?: number;
    onload?: (response: GMXmlHttpRequestResponse) => void;
    onerror?: (response: GMXmlHttpRequestResponse) => void;
    ontimeout?: () => void;
}

declare function GM_xmlhttpRequest(details: GMXmlHttpRequestDetails): void;
