import { useCallback, useRef, useState } from "react";
import { API_URL } from "../../../config";
import type { FormPreview } from "../utils/claimTypes";

const getClaimId = (item: any) =>
  item?.claim_id ||
  item?.claimId ||
  item?.id ||
  item?.payload?.claim_id ||
  item?.payload?.claimId ||
  item?.payload?.id ||
  item?.payload?.claim?.claim_id ||
  item?.payload?.claim?.claimId ||
  item?.payload?.claim?.id ||
  item?.claim?.claim_id ||
  item?.claim?.claimId ||
  item?.claim?.id;

export const useFormPreview = () => {
  const pdfFrameRef = useRef<HTMLIFrameElement>(null);

  const [formPreview, setFormPreview] = useState<FormPreview | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState("");
  const [pdfZoom, setPdfZoom] = useState(100);

  const openFormPreview = useCallback((item: any, form: "CMS1500" | "UB04") => {
    const claimId = getClaimId(item);

    if (!claimId) {
      setPdfError("Unable to open form preview because claim ID is missing.");
      return;
    }

    const path = form === "CMS1500" ? "cms1500" : "ub04";
    const endpointUrl = `${API_URL}/api/claims/${claimId}/${path}`;

    setPdfLoading(true);
    setPdfError("");
    setPdfZoom(100);

    setFormPreview({
      title: `${form} - ${claimId}`,
      claimId,
      form,
      endpointUrl,
      url: endpointUrl,
    });

    window.setTimeout(() => {
      setPdfLoading(false);
    }, 600);
  }, []);

  const closeFormPreview = useCallback(() => {
    setFormPreview(null);
    setPdfError("");
    setPdfLoading(false);
  }, []);

  const printPdfPreview = useCallback(() => {
    if (!formPreview?.url) return;

    try {
      pdfFrameRef.current?.contentWindow?.focus();
      pdfFrameRef.current?.contentWindow?.print();
    } catch {
      window.open(formPreview.url, "_blank", "noopener,noreferrer");
    }
  }, [formPreview]);

  return {
    formPreview,
    setFormPreview,
    pdfLoading,
    setPdfLoading,
    pdfError,
    setPdfError,
    pdfZoom,
    setPdfZoom,
    pdfFrameRef,
    openFormPreview,
    closeFormPreview,
    printPdfPreview,
  };
};