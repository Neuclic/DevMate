import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import { useSessionStore } from "@/store/session-store";

const SESSIONS_QUERY_KEY = ["sessions"] as const;

export function useSessions() {
  const queryClient = useQueryClient();
  const search = useSessionStore((state) => state.sessionSearch);
  const selectedSessionId = useSessionStore((state) => state.selectedSessionId);
  const setSelectedSessionId = useSessionStore((state) => state.setSelectedSessionId);

  const sessionsQuery = useQuery({
    queryKey: [...SESSIONS_QUERY_KEY, search],
    queryFn: () => apiClient.getSessions(search),
    refetchInterval: 30_000,
  });

  const createSession = useMutation({
    mutationFn: (title: string) => apiClient.createSession(title),
    onSuccess: async (session) => {
      setSelectedSessionId(session.id);
      await queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY });
    },
  });

  const deleteSession = useMutation({
    mutationFn: (sessionId: string) => apiClient.deleteSession(sessionId),
    onSuccess: async (_, deletedId) => {
      await queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY });
      if (selectedSessionId === deletedId) {
        setSelectedSessionId(null);
      }
    },
  });

  return {
    ...sessionsQuery,
    createSession,
    deleteSession,
  };
}
