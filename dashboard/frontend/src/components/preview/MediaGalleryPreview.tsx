import type { MediaGalleryComponent } from "../../api/types";

export default function MediaGalleryPreview({ comp }: { comp: MediaGalleryComponent }) {
  const items = comp.items || [];
  return (
    <div className={`dc-media-gallery ${items.length === 1 ? "single" : ""}`}>
      {items.map((item, i) => (
        <div key={i} className="dc-media-item">
          {item.media?.startsWith("https://") ? (
            <img src={item.media} alt={item.description || ""} />
          ) : (
            <span className="dc-media-placeholder">Image</span>
          )}
        </div>
      ))}
    </div>
  );
}
