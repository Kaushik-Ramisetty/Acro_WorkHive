from app.models.role import Role
from app.models.department import Department
from app.models.designation import Designation
from app.models.employee import Employee
from app.models.leave import LeaveType, LeaveBalance, LeaveRequest
from app.models.notification import Notification
from app.models.leave_audit import LeaveAuditLog
from app.models.attendance import Attendance
from app.models.comp_off import CompOffCredit
from app.models.worked_on_leave import WorkedOnLeaveRequest
from app.models.delegate import DelegateAssignment
from app.models.leave_document import LeaveDocument
from app.models.team_capacity import TeamCapacityPolicy, BlackoutPeriod
from app.models.leave_ledger import LeaveBalanceLedger, LedgerTxn
from app.models.leave_accrual_bracket import LeaveAccrualBracket
from app.models.encashment import EncashmentRequest
from app.models.scheduler_health import SchedulerHealth
from app.models.resource_allocation import ResourceAllocation
from app.models.employee_skill import EmployeeSkill
from app.models.team import Team, TeamMember
from app.models.resource_audit import ResourceAllocationAudit

# hrms_schema_complete.xlsx — additive tables
from app.models.shift import (
    Shift,
    AttendancePolicy,
    OvertimeRule,
    EmployeeShift,
    Holiday,
)
from app.models.attendance_records import (
    AttendanceLog,
    ValidationError,
    AttendanceRecord,
    AttendanceException,
    RegularizationRequest,
    RegularizationAttachment,
    OvertimeRecord,
    AttendanceReport,
    PayrollAttendanceSummary,
    WeeklyOffChangeRequest,
)
from app.models.audit_log import AuditLog
from app.models.secure_upload import SecureUpload
from app.models.announcement import Announcement, AnnouncementTarget, AnnouncementRead
from app.models.policy import (
    Policy,
    PolicyVersion,
    PolicyCategory,
    PolicyAcknowledgement,
)
from app.models.project import (
    Project,
    Task,
    Timesheet,
    TimesheetEntry,
    TimesheetPayrollSync,
    TimesheetWorkflowStep,
)

# Onboarding domain
from app.models.onboarding import (
    CandidateStatus,
    CANDIDATE_TRANSITIONS,
    Candidate,
    CandidateDocument,
    DocumentStatus,
    BGVStatus,
    BGVCheck,
    BGVToken,
    OnboardedEmployeeStatus,
    OnboardedEmployee,
    UserRole,
    User,
)

# Finance / Payroll domain
from app.models.monthly_attendance_summary import MonthlyAttendanceSummary
from app.models.payroll_lop_input import PayrollLopInput
from app.models.salary_revision import SalaryRevisionLog
from app.models.salary_hike_request import SalaryHikeRequest
from app.models.bonus_request import BonusRequest
from app.models.off_cycle_payment import OffCyclePayment, OffCycleAuditLog
from app.models.payroll import (
    SalaryStructure,
    PayrollRun,
    PayrollRunEmployee,
    PayrollApproval,
    PayrollError,
    PayrollLockHistory,
)
from app.models.payroll_extended import (
    StatutorySettings,
    PayrollAdjustment,
    EmployeeTaxDeclaration,
    Payslip,
    PayrollAuditLog,
    FinalSettlement,
    SalaryComponent,
    EmployeeSalary,
    TaxDeduction,
    StatutoryDeduction,
    EmployeeSalaryAssignment,
    Reimbursement,
    PayslipDownloadAudit,
    TdsAnnualSummary,
    TdsMonthlyBreakup,
    PayrollVarianceLog,
    DeclarationAuditLog,
)


# Recruitment domain
from app.models.recruitment import (
    JobRequirement,
    RecruitmentCandidate,
    CandidatePipeline,
    InterviewRound,
    InterviewSlot,
    InterviewFeedback,
    RequirementSkill,
)
from app.models.skill_set import SkillSet, SkillRequest

# PMS (Performance Management System)
from app.models.pms_settings import PMSPhaseSettings
from app.models.pms import (
    GoalTemplate,
    TemplateKRA,
    TemplateKPI,
    TemplateCompetency,
    GoalAssignment,
    AssignedKRA,
    AssignedKPI,
    AssignedCompetency,
    GoalComment,
    MidCycleReview,
    KPIProgress,
    ReviewEvidence,
    # Phase 3
    EndCycleAssessment,
    GoalRating,
    CompetencyRating,
    # Phase 4
    NormalizationSession,
    NormalizationRecord,
    # Phase 5
    CompensationRevision,
    PMSCycle,
)

__all__ = [
    "Role", "Department", "Designation", "Employee",
    "LeaveType", "LeaveBalance", "LeaveRequest",
    "Notification", "LeaveAuditLog",
    "Attendance", "CompOffCredit",
    "WorkedOnLeaveRequest", "DelegateAssignment",
    "LeaveDocument", "TeamCapacityPolicy", "BlackoutPeriod",
    "LeaveBalanceLedger", "LedgerTxn", "LeaveAccrualBracket",
    "EncashmentRequest", "SchedulerHealth",
    "ResourceAllocation", "EmployeeSkill",
    "Team", "TeamMember", "ResourceAllocationAudit",
    "Shift", "AttendancePolicy", "OvertimeRule", "EmployeeShift", "Holiday",
    "AttendanceLog", "ValidationError", "AttendanceRecord",
    "AttendanceException", "RegularizationRequest", "RegularizationAttachment",
    "OvertimeRecord", "AttendanceReport", "PayrollAttendanceSummary",
    "WeeklyOffChangeRequest",
    "AuditLog", "SecureUpload",
    "Announcement", "AnnouncementTarget", "AnnouncementRead",
    "Policy", "PolicyVersion", "PolicyCategory", "PolicyAcknowledgement",
    "Project", "Task", "Timesheet", "TimesheetEntry", "TimesheetPayrollSync",
    "TimesheetWorkflowStep",
    "CandidateStatus", "CANDIDATE_TRANSITIONS",
    "Candidate", "CandidateDocument", "DocumentStatus",
    "BGVStatus", "BGVCheck", "BGVToken",
    "OnboardedEmployeeStatus", "OnboardedEmployee",
    "UserRole", "User",
    # Payroll
    "MonthlyAttendanceSummary", "PayrollLopInput",
    "SalaryRevisionLog", "SalaryHikeRequest", "BonusRequest",
    "OffCyclePayment", "OffCycleAuditLog",
    "SalaryStructure", "PayrollRun", "PayrollRunEmployee",
    "PayrollApproval", "PayrollError", "PayrollLockHistory",
    "StatutorySettings", "PayrollAdjustment", "EmployeeTaxDeclaration",
    "Payslip", "PayrollAuditLog", "FinalSettlement",
    "SalaryComponent", "EmployeeSalary", "TaxDeduction",
    "StatutoryDeduction", "EmployeeSalaryAssignment", "Reimbursement",
    "PayslipDownloadAudit", "TdsAnnualSummary", "TdsMonthlyBreakup",
    "PayrollVarianceLog", "DeclarationAuditLog",
    # PMS Phase 1 + 2
    "GoalTemplate", "TemplateKRA", "TemplateKPI", "TemplateCompetency",
    "GoalAssignment", "AssignedKRA", "AssignedKPI", "AssignedCompetency",
    "GoalComment", "MidCycleReview", "KPIProgress", "ReviewEvidence",
    # PMS Phase 3
    "EndCycleAssessment", "GoalRating", "CompetencyRating",
    # PMS Phase 4
    "NormalizationSession", "NormalizationRecord",
    # PMS Phase 5
    "CompensationRevision", "PMSCycle",
    # Recruitment
    "JobRequirement", "RecruitmentCandidate", "CandidatePipeline",
    "InterviewRound", "InterviewSlot", "InterviewFeedback", "RequirementSkill",
    "SkillSet", "SkillRequest",
]
