import { NextResponse } from "next/server";
import OpenAI from "openai";

const MISSING_API_KEY_MESSAGE = "Missing OPENAI_API_KEY environment variable.";
const OPENAI_FAILED_MESSAGE = "OpenAI request failed.";

function responsePayload(reply, overrides = {}) {
  return {
    reply,
    ai_configured: false,
    used_key_source: "none",
    client_keys_allowed: false,
    ...overrides,
  };
}

export async function POST(request) {
  try {
    const { prompt } = await request.json();
    const serverApiKey = String(process.env.OPENAI_API_KEY || "").trim();

    if (!serverApiKey) {
      return NextResponse.json(
        responsePayload(MISSING_API_KEY_MESSAGE, {
          error_code: "server_key_missing",
        }),
        { status: 503 }
      );
    }

    const openai = new OpenAI({ apiKey: serverApiKey });

    const completion = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: prompt }],
    });

    const reply = completion.choices[0].message.content;
    return NextResponse.json(
      responsePayload(reply, {
        ai_configured: true,
        used_key_source: "server",
      })
    );
  } catch {
    return NextResponse.json(
      responsePayload(OPENAI_FAILED_MESSAGE, {
        error_code: "openai_request_failed",
      }),
      { status: 500 }
    );
  }
}
