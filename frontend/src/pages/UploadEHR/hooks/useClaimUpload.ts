import { useCallback, useRef, useState } from "react";
import { API_URL } from "../../../config";
import type { ProcessingMode, UploadStatus } from "../utils/claimTypes";

type UseClaimUploadOptions = {
  processingMode: ProcessingMode;
  onUpload?: (data: any) => void;
  refreshClaims?: () => Promise<any[]>;
  mergeItems?: (claims: any[]) => void;
  markClaimAsNew?: (claimId: string) => void;
};

const getClaimId = (item: any) =>
  item?.claim_id ||
  item?.id ||
  item?.claimId ||
  item?.payload?.claim_id ||
  item?.payload?.claim?.claim_id ||
  item?.claim?.claim_id;

const getUploadSource = (file: File | null) => {
  if (!file) return "Not reported";

  const ext = file.name.split(".").pop()?.toLowerCase() || "";

  if (ext === "pdf") return "PDF";
  if (["png", "jpg", "jpeg", "webp", "tif", "tiff"].includes(ext)) return "IMAGE";
  if (["xls", "xlsx", "csv"].includes(ext)) return "BULK";

  return ext.toUpperCase() || "FILE";
};

export const useClaimUpload = ({
  processingMode,
  onUpload,
  refreshClaims,
  mergeItems,
  markClaimAsNew,
}: UseClaimUploadOptions) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("idle");
  const [uploadMessage, setUploadMessage] = useState("");

  const handleFileChange = useCallback((selected: File | null) => {
    setFile(selected);
    setUploadStatus("idle");
    setUploadMessage("");
  }, []);

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const clearSelectedFile = useCallback(() => {
    setFile(null);
  }, []);

  const handleUpload = useCallback(
    async (event?: React.FormEvent) => {
      event?.preventDefault();

      if (!file) {
        fileInputRef.current?.click();
        return;
      }

      const formData = new FormData();
      const uploadSessionId =
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `SESSION-${Date.now()}`;
      const tempId = `TEMP-${Date.now()}`;

      formData.append("file", file);
      formData.append("processing_mode", processingMode);
      formData.append("upload_session_id", uploadSessionId);
      formData.append("temp_id", tempId);

      try {
        setLoading(true);
        setUploadStatus("loading");
        setUploadMessage("Pipeline orchestration in progress");

        const response = await fetch(`${API_URL}/intake/upload`, {
          method: "POST",
          body: formData,
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
          throw new Error(data?.detail || data?.message || "Upload failed");
        }

        const claimData = data?.claim || data?.payload?.claim || data;
        const claimId = getClaimId(claimData) || data?.claim_id;

        if (claimId && mergeItems) {
          const now = new Date().toISOString();

          mergeItems([
            {
              ...claimData,
              claim_id: claimId,
              id: claimId,
              status: "QUEUED",
              stage: "UPLOAD_API",
              current_stage: "UPLOAD_API",
              current_agent: "Upload Api",
              active_step: "upload",
              pipeline_state: "QUEUED",
              pipeline_status: "QUEUED",
              progress: 5,
              upload_mode: "single",
              upload_source: getUploadSource(file),
              processing_mode: processingMode,
              is_new_upload: true,
              __queued_placeholder: true,
              uploaded_at: now,
              updatedAt: now,
              last_activity_at: now,
            },
          ]);

          markClaimAsNew?.(claimId);

          [1500, 3000, 6000, 10000].forEach((delayMs) => {
            window.setTimeout(() => {
              void refreshClaims?.();
            }, delayMs);
          });
        } else {
          await refreshClaims?.();
        }

        onUpload?.(claimData);

        setUploadStatus("success");
        setUploadMessage("Upload complete. Claim intake started.");
        setFile(null);

        return data;
      } catch (error: any) {
        console.error("[upload] failed", error);
        setUploadStatus("error");
        setUploadMessage(error?.message || "Upload failed. Please try again.");
        return null;
      } finally {
        setLoading(false);
      }
    },
    [file, processingMode, mergeItems, markClaimAsNew, refreshClaims, onUpload]
  );

  return {
    file,
    setFile,
    fileInputRef,
    loading,
    uploadStatus,
    uploadMessage,
    handleFileChange,
    handleUpload,
    openFilePicker,
    clearSelectedFile,
  };
};
