import { useApp } from "../AppContext";
import RequestWFHDialog from "../../../components/RequestWFHDialog";

// Thin AppContext-aware wrapper. Real UI lives in components/RequestWFHDialog
// so all three role dashboards share the same form.
const RequestWFHModal = () => {
  const { closeModal } = useApp();
  return <RequestWFHDialog open={true} onClose={closeModal} onSubmitted={() => {}} />;
};

export default RequestWFHModal;
