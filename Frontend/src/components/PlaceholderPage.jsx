import PageHeader from './PageHeader';
import Card from './Card';
import Icon from './Icon';

export default function PlaceholderPage({ title, subtitle, icon = 'doc' }) {
  return (
    <div>
      <PageHeader title={title} subtitle={subtitle} />
      <Card>
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
            <Icon name={icon} className="h-7 w-7" />
          </div>
          <h2 className="mt-4 text-lg font-semibold text-slate-900">{title}</h2>
          <p className="mt-1 max-w-md text-sm text-slate-500">
            This module is part of your role-based workspace. The page is wired into the routing and layout - content for this section will live here.
          </p>
        </div>
      </Card>
    </div>
  );
}
