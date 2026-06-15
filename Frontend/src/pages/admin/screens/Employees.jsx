import { useState } from 'react'

const EMPLOYEES = [
  { id: 1, name: 'Sarah Jenkins', role: 'UX Designer', dept: 'Product', status: 'Active', joined: '2022-03-15', email: 'sarah.j@workhive.com', initials: 'SJ', color: '#6366F1' },
  { id: 2, name: 'Michael Chen', role: 'Data Analyst', dept: 'Analytics', status: 'Active', joined: '2021-07-20', email: 'michael.c@workhive.com', initials: 'MC', color: '#10B981' },
  { id: 3, name: 'Emma Thompson', role: 'HR Manager', dept: 'Human Resources', status: 'Active', joined: '2020-01-10', email: 'emma.t@workhive.com', initials: 'ET', color: '#F59E0B' },
  { id: 4, name: 'James Wilson', role: 'Backend Engineer', dept: 'Engineering', status: 'Active', joined: '2023-05-01', email: 'james.w@workhive.com', initials: 'JW', color: '#3B5BDB' },
  { id: 5, name: 'Priya Nair', role: 'Product Manager', dept: 'Product', status: 'On Leave', joined: '2019-11-22', email: 'priya.n@workhive.com', initials: 'PN', color: '#EF4444' },
  { id: 6, name: 'David Park', role: 'DevOps Engineer', dept: 'Engineering', status: 'Active', joined: '2022-08-14', email: 'david.p@workhive.com', initials: 'DP', color: '#8B5CF6' },
  { id: 7, name: 'Anjali Mehta', role: 'Marketing Lead', dept: 'Marketing', status: 'Active', joined: '2021-03-30', email: 'anjali.m@workhive.com', initials: 'AM', color: '#06B6D4' },
  { id: 8, name: 'Robert Lee', role: 'Finance Analyst', dept: 'Finance', status: 'Inactive', joined: '2018-06-05', email: 'robert.l@workhive.com', initials: 'RL', color: '#F97316' },
]

export default function Employees() {
  const [search, setSearch] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [filterDept, setFilterDept] = useState('All')

  const depts = ['All', ...new Set(EMPLOYEES.map(e => e.dept))]
  const filtered = EMPLOYEES.filter(e =>
    (filterDept === 'All' || e.dept === filterDept) &&
    (e.name.toLowerCase().includes(search.toLowerCase()) || e.role.toLowerCase().includes(search.toLowerCase()))
  )

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Employees</h1>
          <p>Manage all employee records and profiles</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          <span>+</span> Add Employee
        </button>
      </div>

      {/* Filters */}
      <div className="card" style={{ padding: '16px 20px', marginBottom: 20, display: 'flex', gap: 12, alignItems: 'center' }}>
        <input type="text" placeholder="Search by name or role..." value={search} onChange={e => setSearch(e.target.value)} style={{ maxWidth: 300 }} />
        <select value={filterDept} onChange={e => setFilterDept(e.target.value)} style={{ maxWidth: 180 }}>
          {depts.map(d => <option key={d}>{d}</option>)}
        </select>
        <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-muted)' }}>{filtered.length} employees</span>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Employee</th>
              <th>Role</th>
              <th>Department</th>
              <th>Status</th>
              <th>Joined</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(emp => (
              <tr key={emp.id}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 34, height: 34, borderRadius: '50%', background: emp.color, color: '#fff', fontSize: 12, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{emp.initials}</div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{emp.name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{emp.email}</div>
                    </div>
                  </div>
                </td>
                <td style={{ fontSize: 14 }}>{emp.role}</td>
                <td><span className="badge badge-blue">{emp.dept}</span></td>
                <td>
                  <span className={`badge ${emp.status === 'Active' ? 'badge-green' : emp.status === 'On Leave' ? 'badge-orange' : 'badge-gray'}`}>
                    {emp.status}
                  </span>
                </td>
                <td style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{emp.joined}</td>
                <td>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-outline" style={{ padding: '5px 12px', fontSize: 12 }}>View</button>
                    <button className="btn btn-ghost" style={{ padding: '5px 12px', fontSize: 12 }}>Edit</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showModal && <AddEmployeeModal onClose={() => setShowModal(false)} />}
    </div>
  )
}

function AddEmployeeModal({ onClose }) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div className="card fade-in" style={{ width: 520, padding: 32, maxHeight: '90vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700 }}>Add New Employee</h2>
          <button className="btn btn-ghost" style={{ padding: '4px 8px' }} onClick={onClose}>✕</button>
        </div>
        <div className="form-row">
          <div className="form-group"><label>First Name</label><input type="text" placeholder="John" /></div>
          <div className="form-group"><label>Last Name</label><input type="text" placeholder="Doe" /></div>
        </div>
        <div className="form-group"><label>Email</label><input type="email" placeholder="john.doe@workhive.com" /></div>
        <div className="form-row">
          <div className="form-group"><label>Department</label><select><option>Engineering</option><option>Product</option><option>HR</option><option>Finance</option><option>Marketing</option></select></div>
          <div className="form-group"><label>Role</label><input type="text" placeholder="e.g. Software Engineer" /></div>
        </div>
        <div className="form-row">
          <div className="form-group"><label>Join Date</label><input type="date" /></div>
          <div className="form-group"><label>Employment Type</label><select><option>Full-time</option><option>Part-time</option><option>Contract</option></select></div>
        </div>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 8 }}>
          <button className="btn btn-outline" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={onClose}>Save Employee</button>
        </div>
      </div>
    </div>
  )
}
