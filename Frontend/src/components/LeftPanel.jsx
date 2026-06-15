import logo from '../assets/logo.png';

export default function LeftPanel() {
  return (
    <div className="relative h-full w-full overflow-hidden rounded-l-2xl bg-gradient-to-br from-[#1e3acb] via-[#1a31b3] to-[#172579] p-10 text-white md:p-12">
      <div
        aria-hidden
        className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/10 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-white/5 blur-3xl"
      />

      <div className="relative z-10 flex items-center gap-2.5">
        <img
          src={logo}
          alt="WorkHive logo"
          className="h-8 w-8 rounded-md bg-white object-contain shadow-sm"
        />
        <span className="text-base font-semibold tracking-tight">WorkHive</span>
      </div>

      <div className="relative z-10 mt-24 max-w-sm md:mt-32">
        <h1 className="text-3xl font-bold leading-tight tracking-tight md:text-4xl">
          Welcome to<br />
          your{' '}
          <span className="text-emerald-300">employee hub</span>
          <span className="text-white">.</span>
        </h1>
        <p className="mt-5 text-sm leading-relaxed text-white/75 md:text-[15px]">
          Access your payroll, benefits, and<br className="hidden md:block" />
          professional development tools<br className="hidden md:block" />
          through our encrypted gateway.
        </p>
      </div>
    </div>
  );
}
