export function getNextTabIndex(
  currentIndex: number,
  key: string,
  tabCount: number,
): number | null {
  if (tabCount < 1) return null;
  if (key === "Home") return 0;
  if (key === "End") return tabCount - 1;
  if (key === "ArrowRight") return (currentIndex + 1) % tabCount;
  if (key === "ArrowLeft") return (currentIndex - 1 + tabCount) % tabCount;
  return null;
}
