import { Card } from '@/components/ui'
import { HiChartBar, HiClock, HiUsers } from 'react-icons/hi2'

export default function Dashboard() {
  return (
    <div className="max-w-7xl mx-auto animate-fade-in">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-primary-950 mb-2">Dashboard</h2>
        <p className="text-primary-600">Vue d'ensemble de vos statistiques et métriques</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <StatCard
          icon={HiChartBar}
          title="Conversations"
          value="0"
          subtitle="Aucune conversation enregistrée"
        />
        <StatCard
          icon={HiUsers}
          title="Utilisateurs"
          value="—"
          subtitle="Statistiques à venir"
        />
        <StatCard
          icon={HiClock}
          title="Temps moyen"
          value="—"
          subtitle="Données non disponibles"
        />
      </div>

      <Card variant="elevated" className="text-center py-12">
        <HiChartBar className="w-16 h-16 mx-auto mb-4 text-primary-300" />
        <h3 className="text-xl font-semibold text-primary-950 mb-2">
          Graphiques et KPI à venir
        </h3>
        <p className="text-primary-600">
          Cette section affichera bientôt des graphiques détaillés et des indicateurs de performance.
        </p>
      </Card>
    </div>
  )
}

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>
  title: string
  value: string
  subtitle: string
}

function StatCard({ icon: Icon, title, value, subtitle }: StatCardProps) {
  return (
    <Card variant="elevated" className="hover:shadow-xl transition-shadow duration-200">
      <div className="flex items-start gap-4">
        <div className="p-3 bg-primary-950 rounded-lg">
          <Icon className="w-6 h-6 text-white" />
        </div>
        <div className="flex-1">
          <p className="text-sm text-primary-600 mb-1">{title}</p>
          <p className="text-2xl font-bold text-primary-950 mb-1">{value}</p>
          <p className="text-xs text-primary-500">{subtitle}</p>
        </div>
      </div>
    </Card>
  )
}
