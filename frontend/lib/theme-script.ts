// Shared with the server-rendered root layout, so not a client module.

export const THEME_KEY = "vros-theme";

/** Runs before first paint: resolve the saved theme choice so a dark page never flashes white. */
export const THEME_SCRIPT = `(function(){try{var c=localStorage.getItem("${THEME_KEY}")||"system";var d=c==="dark"||(c==="system"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.dataset.theme=d?"dark":"light"}catch(e){}})()`;
