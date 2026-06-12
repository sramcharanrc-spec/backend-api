import { Printer, X, ZoomIn, ZoomOut } from "lucide-react";
import type { FormPreview } from "../utils/claimTypes";

type FormPreviewModalProps = {
  formPreview: FormPreview | null;
  pdfLoading: boolean;
  pdfError: string;
  pdfZoom: number;
  setPdfZoom: (updater: number | ((prev: number) => number)) => void;
  setFormPreview: (preview: FormPreview | null) => void;
  printPdfPreview: () => void;
  pdfFrameRef: React.RefObject<HTMLIFrameElement>;
};

const FormPreviewModal = ({
  formPreview,
  pdfLoading,
  pdfError,
  pdfZoom,
  setPdfZoom,
  setFormPreview,
  printPdfPreview,
  pdfFrameRef,
}: FormPreviewModalProps) => {
  if (!formPreview) return null;

  const previewUrl = formPreview.url || formPreview.endpointUrl;

  return (
    <div className="cw-modal-backdrop">
      <div className="cw-modal cw-form-preview-modal">
        <div className="cw-modal-head">
          <div>
            <h3>{formPreview.title}</h3>
            <span>{formPreview.claimId}</span>
          </div>

          <div className="cw-modal-tools">
            <button type="button" onClick={() => setPdfZoom((prev) => Math.max(50, prev - 10))}>
              <ZoomOut size={16} />
            </button>

            <span>{pdfZoom}%</span>

            <button type="button" onClick={() => setPdfZoom((prev) => Math.min(200, prev + 10))}>
              <ZoomIn size={16} />
            </button>

            <button type="button" onClick={printPdfPreview}>
              <Printer size={16} />
            </button>

            <button type="button" onClick={() => setFormPreview(null)}>
              <X size={16} />
            </button>
          </div>
        </div>

        {pdfLoading && <div className="cw-pdf-state">Loading preview...</div>}

        {pdfError && <div className="cw-pdf-error">{pdfError}</div>}

        {!pdfError && previewUrl && (
          <div className="cw-pdf-frame-wrap" style={{ transform: `scale(${pdfZoom / 100})` }}>
            <iframe
              ref={pdfFrameRef}
              title={formPreview.title}
              src={previewUrl}
              className="cw-pdf-frame"
              onLoad={() => {
                // Loading state is controlled by parent for CMS1500.
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default FormPreviewModal;