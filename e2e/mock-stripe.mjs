// Minimal mock of the Stripe REST API for E2E. The API server is pointed here
// via STRIPE_API_BASE, so createCheckout/createCreditCheckout/createPortal work
// without real Stripe credentials. Webhook events are NOT produced here — the
// specs POST signed event JSON straight to /api/stripe-webhook.
import { createServer } from "node:http";

let seq = 0;

createServer((req, res) => {
  const url = req.url ?? "";
  const json = (body) => {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(body));
  };
  // drain the (form-encoded) body; contents don't matter for the mock
  let b = "";
  req.on("data", (d) => (b += d));
  req.on("end", () => {
    if (req.method === "GET" && url.startsWith("/health")) {
      return json({ ok: true });
    }
    if (req.method === "POST" && url.startsWith("/v1/customers")) {
      return json({ id: `cus_mock_${++seq}`, object: "customer" });
    }
    if (req.method === "POST" && url.startsWith("/v1/checkout/sessions")) {
      const id = `cs_mock_${++seq}`;
      return json({
        id,
        object: "checkout.session",
        url: `https://checkout.stripe.mock/pay/${id}`,
      });
    }
    if (req.method === "POST" && url.startsWith("/v1/billing_portal/sessions")) {
      return json({
        id: `bps_mock_${++seq}`,
        object: "billing_portal.session",
        url: "https://billing.stripe.mock/portal",
      });
    }
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { message: `mock stripe: no route ${url}` } }));
  });
}).listen(9098, () => console.log("mock stripe on :9098"));
