import { useApp } from "../AppContext";
import ApplyLeaveDialog from "../../../components/ApplyLeaveDialog";

// Thin AppContext-aware wrapper. The actual modal UI now lives in
// components/ApplyLeaveDialog so admin / manager / employee all share the
// same look and behaviour.
const ApplyLeaveModal = () => {
  const { closeModal } = useApp();
  return <ApplyLeaveDialog open={true} onClose={closeModal} onSubmitted={() => {}} />;
};

export default ApplyLeaveModal;
