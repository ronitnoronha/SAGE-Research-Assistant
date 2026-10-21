-- ==========================================================
-- SAGE MIGRATION 002 - PRIVATE PER-USER LIBRARIES + ROW LEVEL SECURITY
-- Run once in Supabase -> SQL Editor BEFORE deploying the matching backend.
-- Safe to run while the old backend is still live.
-- ==========================================================

-- 1. Record who owns each chunk (deleting a user deletes their chunks)
ALTER TABLE public.documents
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS documents_user_id_idx ON public.documents (user_id);
CREATE INDEX IF NOT EXISTS documents_user_source_idx ON public.documents (user_id, (metadata->>'source'));

-- 2. Row Level Security: the public (publishable) key can only ever see a signed-in user's own rows.
--    The backend uses the secret key, which bypasses RLS and filters by user_id itself.
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users read their own chunks" ON public.documents;
CREATE POLICY "Users read their own chunks"
    ON public.documents FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- 3. User-scoped similarity search used by the new backend
CREATE OR REPLACE FUNCTION match_user_documents (
  query_embedding VECTOR(384),
  filter_user_id UUID,
  match_threshold FLOAT DEFAULT 0.3,
  match_count INT DEFAULT 5
)
RETURNS TABLE (
  id BIGINT,
  content TEXT,
  metadata JSONB,
  similarity FLOAT
)
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  SELECT
    documents.id,
    documents.content,
    documents.metadata,
    1 - (documents.embedding <=> query_embedding) AS similarity
  FROM documents
  WHERE documents.user_id = filter_user_id
    AND 1 - (documents.embedding <=> query_embedding) > match_threshold
  ORDER BY documents.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Only the backend (secret key) may call the search functions directly
REVOKE EXECUTE ON FUNCTION match_user_documents(VECTOR, UUID, FLOAT, INT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION match_documents(VECTOR, FLOAT, INT) FROM PUBLIC, anon, authenticated;

-- 4. Existing chunks were uploaded before ownership existed (user_id is NULL), so nobody sees them now.
--    To keep your own documents, uncomment and set your sign-in email:
-- UPDATE public.documents
--    SET user_id = (SELECT id FROM auth.users WHERE email = 'you@example.com')
--  WHERE user_id IS NULL
--    AND metadata->>'source' IN ('insulin.pdf', 'ADA_Standards_2022_Diabetes.pdf');
--
--    Anything left without an owner can then be removed:
-- DELETE FROM public.documents WHERE user_id IS NULL;

-- 5. After the new backend is live, the old unscoped search function can be dropped:
-- DROP FUNCTION IF EXISTS match_documents(VECTOR, FLOAT, INT);
