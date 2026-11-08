import { articleCount } from "@/lib/articles";
import catalog from "@/content/catalog.json";
export async function GET() {
  try {
    const count = articleCount();
    const ok = count === catalog.length && count > 0;
    return Response.json({ status: ok ? "ok" : "unavailable", articles: count,
      commit: process.env.DEPLOY_COMMIT || "local" }, { status: ok ? 200 : 503 });
  } catch { return Response.json({ status: "unavailable" }, { status: 503 }); }
}
