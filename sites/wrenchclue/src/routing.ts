import path from 'node:path';
export function safeStaticPath(root:string,pathname:string):string|null {
  let decoded:string;
  try{decoded=decodeURIComponent(pathname);}catch{return null;}
  if(decoded.includes('\0')||decoded.includes('\\'))return null;
  const resolved=path.resolve(root,'.'+decoded);
  if(resolved!==path.resolve(root)&&!resolved.startsWith(path.resolve(root)+path.sep))return null;
  return resolved;
}
export function isPrivatePath(pathname:string):boolean {
  try{pathname=decodeURIComponent(pathname);}catch{return true;}
  return pathname==='/manifest.json'||pathname.startsWith('/api/')||/(?:^|\/)\./.test(pathname);
}
