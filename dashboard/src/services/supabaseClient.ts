import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey);

export const supabase = isSupabaseConfigured
  ? createClient(supabaseUrl as string, supabaseAnonKey as string, {
      auth: {
        persistSession: false,
        autoRefreshToken: false,
      },
      db: {
        schema: "public",
      },
      global: {
        headers: {
          "X-Client-Info": "swing-ai-dashboard",
        },
      },
      realtime: {
        params: {
          eventsPerSecond: 10,
        },
      },
    })
  : null;

/**
 * Validates the core heartbeat connectivity to the Supabase backend.
 */
export async function testSupabaseConnection(): Promise<{ success: boolean; error?: string }> {
  if (!supabase) {
    return { success: false, error: "Supabase not configured" };
  }

  try {
    const { error } = await supabase.from("current_portfolio").select("count", { count: "exact", head: true });
    if (error) throw error;
    return { success: true };
  } catch (err) {
    return { success: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

/**
 * NEW: Dynamic fetch utility to grab the live market state tracker token
 * for rendering active session states directly inside dashboard components.
 */
export async function getMarketStatus(): Promise<string> {
  if (!supabase) {
    return "DISCONNECTED";
  }

  try {
    const { data, error } = await supabase
      .from("system_state")
      .select("value")
      .eq("key", "market_status")
      .maybeSingle(); // Safely handles empty tables without throwing unhandled exceptions

    if (error) throw error;
    return data ? (data.value as string) : "UNKNOWN";
  } catch (err) {
    console.error("Failed to extract active market tracking vectors:", err);
    return "UNKNOWN";
  }
}
