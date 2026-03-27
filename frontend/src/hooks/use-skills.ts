import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";

export function useSkills(search: string, type?: string) {
  return useQuery({
    queryKey: ["skills", search, type ?? "all"],
    queryFn: () => apiClient.getSkills({ search, ...(type ? { type } : {}) }),
    retry: 1,
  });
}
