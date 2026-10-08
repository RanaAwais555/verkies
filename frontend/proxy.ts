import { NextResponse, type NextRequest } from "next/server";

// Optimistic check only: send people without a session cookie to the sign-in page before the
// app loads. The API decides who is signed in and what they may see (backend/app/auth/deps.py).
const SESSION_COOKIES = ["__Host-vros_session", "vros_session"];

export function proxy(request: NextRequest) {
  if (SESSION_COOKIES.some((name) => request.cookies.has(name))) return NextResponse.next();
  const login = new URL("/login", request.url);
  const here = request.nextUrl.pathname + request.nextUrl.search;
  if (here !== "/") login.searchParams.set("next", here);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except the public pages, the API, Next's assets and static files.
  matcher: ["/((?!login|invite|api|_next/|favicon\\.ico|.*\\.[a-z0-9]+$).*)"],
};
