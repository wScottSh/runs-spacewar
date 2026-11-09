import type { Net } from './model'
import { chanceTies, shapesOf } from './geometry'
import { routeArcs } from './route'

const scope = self as unknown as { onmessage: (e: MessageEvent<{ id: number; net: Net }>) => void; postMessage: (m: unknown) => void }

scope.onmessage = (e) => {
  const { id, net } = e.data
  scope.postMessage({ id, routes: [...routeArcs(net, shapesOf(net, chanceTies(net)))] })
}
