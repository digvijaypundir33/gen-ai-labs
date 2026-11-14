import { Amplify } from "aws-amplify";

export const REST_BASE = "https://ll4f40het1.execute-api.us-east-1.amazonaws.com/prod";
export const WS_URL = "wss://tbex2czo8h.execute-api.us-east-1.amazonaws.com/prod";

Amplify.configure({
  API: {
    REST: {
      supportApi: {
        endpoint: REST_BASE,
        region: "us-east-1",
      },
    },
  },
});
