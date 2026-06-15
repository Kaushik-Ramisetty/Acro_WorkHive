// View-only avatar display. Renders the user's initials inside a coloured
// circle with a small "online" indicator at the bottom-right. The upload
// affordance was removed so the profile header reads cleanly.
export default function AvatarUpload({ initials = 'U', size = 88, gradient = 'from-blue-500 to-indigo-600' }) {
  return (
    <div className="relative inline-block">
      <div
        className={'flex items-center justify-center rounded-full text-white font-bold ring-4 ring-white shadow-md bg-gradient-to-br ' + gradient}
        style={{ width: size, height: size, fontSize: size * 0.36 }}
      >
        {initials}
      </div>
      <span className="absolute bottom-2 right-2 h-4 w-4 rounded-full bg-emerald-500 ring-2 ring-white shadow-sm" />
    </div>
  );
}
