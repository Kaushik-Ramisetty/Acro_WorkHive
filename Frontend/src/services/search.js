import { api } from './api';

export const searchApi = {
  query: (q) => api.get('/search?q=' + encodeURIComponent(q || '') + '&limit=5'),
};
