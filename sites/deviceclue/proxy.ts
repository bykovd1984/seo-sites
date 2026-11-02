import { NextRequest, NextResponse } from 'next/server';
import { pageResponse, prefersMarkdown } from './lib/agent-content.mjs';
import { site } from './lib/site';

export async function proxy(request: NextRequest) {
  if (!['GET', 'HEAD'].includes(request.method)) return NextResponse.next();
  if (request.nextUrl.searchParams.get('__agent_html') === '1') {
    return NextResponse.next();
  }
  if (request.headers.get('rsc') === '1') return NextResponse.next();
  return pageResponse(request, site.url, prefersMarkdown(request.headers.get('accept') || ''));
}

export const config = { matcher: ['/', '/about', '/privacy', '/guides/:slug', '/topics/:category'] };
