variable "ecs_cluster_arn" { type = string }
variable "ecs_task_definition_arn" { type = string }
variable "ecs_subnets" { type = list(string) }
variable "ecs_security_group_id" { type = string }
variable "ecs_task_execution_role_arn" { type = string }
variable "ecs_task_role_arn" { type = string }