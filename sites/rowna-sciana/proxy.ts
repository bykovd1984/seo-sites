import { NextRequest, NextResponse } from 'next/server';
import { pageResponse, prefersMarkdown } from './lib/agent-content.mjs';
import { SITE_URL } from './lib/site';

export async function proxy(request: NextRequest) {
  if (!['GET', 'HEAD'].includes(request.method)) return NextResponse.next();
  if (request.nextUrl.searchParams.get('__agent_html') === '1') {
    return NextResponse.next();
  }
  if (request.headers.get('rsc') === '1') return NextResponse.next();
  return pageResponse(request, SITE_URL, prefersMarkdown(request.headers.get('accept') || ''));
}

export const config = { matcher: ['/', '/o-poradniku', '/prywatnosc', '/poradniki/:slug'] };
