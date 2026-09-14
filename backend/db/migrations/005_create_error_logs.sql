CREATE TABLE IF NOT EXISTS public.error_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    user_id UUID,
    context JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

ALTER TABLE IF EXISTS public.error_logs ENABLE ROW LEVEL SECURITY;

-- Allow inserts from authenticated and anon users (via backend)
CREATE POLICY "Enable insert for authenticated users only"
ON public.error_logs
FOR INSERT TO authenticated, anon
WITH CHECK (true);
