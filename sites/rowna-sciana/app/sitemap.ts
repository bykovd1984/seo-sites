import catalog from "@/content/catalog.json";
import { SITE_URL } from "@/lib/site";
export default function sitemap() {
 return ["/","/o-poradniku","/prywatnosc",...catalog.map(a=>"/poradniki/"+a.slug)].map(path=>({url:SITE_URL+path}));
}
