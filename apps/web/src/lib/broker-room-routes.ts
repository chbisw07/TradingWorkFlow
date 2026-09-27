import { brokerProviders } from "./broker-setup";
import { roomViews, type RoomView } from "./portfolio";

// The same resolver governs route rendering and every operational account link.
export function resolveBrokerRoom(path: readonly string[]) {
  if (path.length !== 3) return null;
  const [providerId, accountId, view] = path;
  const provider = brokerProviders.find(
    (value) => value.provider_id === providerId,
  );
  if (
    provider?.operational_room !== "ZERODHA" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      accountId,
    ) ||
    !roomViews.includes(view as RoomView)
  )
    return null;
  return { accountId, view: view as RoomView };
}

export function brokerRoomHref(providerId: string, accountId: string) {
  const path = [providerId, accountId, "dashboard"];
  return resolveBrokerRoom(path) ? `/brokers/${path.join("/")}` : null;
}
