output "cluster_arn" {
  value = aws_ecs_cluster.scraper_cluster.arn
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.scraper_task.arn
}

output "subnets" {
  value = data.aws_subnets.default.ids
}

output "security_group_id" {
  value = aws_security_group.scraper_sg.id
}

output "ecs_task_execution_role_arn" {
  value = aws_iam_role.ecs_task_execution_role.arn
}

output "ecs_task_role_arn" {
  value = aws_iam_role.ecs_task_role.arn
}
