// Stand-in for the 'cesium' package: the satellites layer's update path only constructs values and calls static
// helpers on these seven names; nothing it computes with them is read back by the harness.
const anything = new Proxy(function () {}, {
  get: (t, p) => (p === Symbol.toPrimitive ? () => 0 : anything),
  apply: () => anything,
  construct: () => anything,
});
export const Cartesian3 = anything, Color = anything, Matrix4 = anything, Matrix3 = anything, Cartographic = anything, NearFarScalar = anything;
const CesiumMath = anything;
export { CesiumMath as Math };
export default { Cartesian3, Color, Matrix4, Matrix3, Cartographic, NearFarScalar, Math: CesiumMath };
