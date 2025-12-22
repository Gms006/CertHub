export const API_BASE =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

type ApiClientOptions = {
  baseUrl?: string;
  getAccessToken: () => string | null;
  refreshAccessToken: () => Promise<string | null>;
};

const withBaseUrl = (baseUrl: string, input: RequestInfo | URL) => {
  if (typeof input !== "string") {
    return input;
  }
  if (input.startsWith("http")) {
    return input;
  }
  return `${baseUrl}${input.startsWith("/") ? input : `/${input}`}`;
};

export const createApiClient = ({
  baseUrl = API_BASE,
  getAccessToken,
  refreshAccessToken,
}: ApiClientOptions) => {
  return async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const execute = async (token?: string | null) => {
      const headers = new Headers(init.headers);
      if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      }
      return fetch(withBaseUrl(baseUrl, input), {
        ...init,
        headers,
        credentials: init.credentials ?? "include",
      });
    };

    const response = await execute(getAccessToken());
    if (response.status !== 401) {
      return response;
    }

    const refreshedToken = await refreshAccessToken();
    if (!refreshedToken) {
      return response;
    }

    return execute(refreshedToken);
  };
};
