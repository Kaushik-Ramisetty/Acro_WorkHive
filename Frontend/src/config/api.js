/**
 * Compatibility shim. The merged Frontend uses Core's services/api.js as the
 * canonical HTTP client. Onboarding-side services (candidateApi.js,
 * onboardingApi.js, vendorApi.js) import { BASE / API_BASE_URL } from this
 * file — keep the export names so those files stay untouched.
 */
import { API_BASE_URL as CORE_API_BASE } from '../services/api';

export const API_BASE_URL = CORE_API_BASE;
export const BASE = CORE_API_BASE;
export const BASE_URL = CORE_API_BASE;
export const API_BASE = CORE_API_BASE;
