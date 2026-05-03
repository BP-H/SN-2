import path from "node:path";
import { readFile } from "node:fs/promises";

export async function GET() {
  const htmlPath = path.join(process.cwd(), "public", "about.html");
  const html = await readFile(htmlPath, "utf8");
  return new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "public, max-age=0, must-revalidate",
    },
  });
}
