import { articleCount } from '@/lib/articles';
export async function GET(){return Response.json({status:'ok',site:'deviceclue',articles:articleCount(),publication:'public',commit:process.env.DEPLOY_COMMIT||'local'},{headers:{'Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow'}});}
