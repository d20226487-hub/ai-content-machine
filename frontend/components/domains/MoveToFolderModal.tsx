// Re-export the shared modal — kept at this path so existing imports
// (`@/components/domains/MoveToFolderModal`) keep working. New callers
// should import directly from `@/components/folders/MoveToFolderModal`.
export { MoveToFolderModal } from "@/components/folders/MoveToFolderModal";
